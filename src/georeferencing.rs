use crate::{
    model::{GeoreferencingData, MapConversion, ProjectedCrs},
    parser::{number, numbers, reference, string, ParsedModel},
    units::resolve_unit,
};

pub(crate) fn build_georeferencing(model: &ParsedModel) -> GeoreferencingData {
    let map_conversion = model
        .entity_types
        .iter()
        .find(|(_, type_name)| {
            matches!(
                type_name.as_str(),
                "IFCMAPCONVERSION" | "IFCMAPCONVERSIONSCALED"
            )
        })
        .and_then(|(id, type_name)| {
            let record = model.records.get(id)?;
            Some(MapConversion {
                express_id: *id,
                ifc_type: if type_name == "IFCMAPCONVERSIONSCALED" {
                    "IfcMapConversionScaled"
                } else {
                    "IfcMapConversion"
                }
                .to_string(),
                source_crs_id: reference(record.attributes.first()),
                target_crs_id: reference(record.attributes.get(1)),
                eastings: number(record.attributes.get(2))?,
                northings: number(record.attributes.get(3))?,
                orthogonal_height: number(record.attributes.get(4))?,
                x_axis_abscissa: number(record.attributes.get(5)),
                x_axis_ordinate: number(record.attributes.get(6)),
                scale: number(record.attributes.get(7)),
                factor_x: number(record.attributes.get(8)),
                factor_y: number(record.attributes.get(9)),
                factor_z: number(record.attributes.get(10)),
            })
        });

    let projected_crs = model
        .entity_types
        .iter()
        .find(|(_, type_name)| type_name.as_str() == "IFCPROJECTEDCRS")
        .and_then(|(id, _)| {
            let record = model.records.get(id)?;
            let map_unit_id = reference(record.attributes.get(6));
            let unit = map_unit_id.and_then(|unit_id| resolve_unit(model, unit_id));
            Some(ProjectedCrs {
                express_id: *id,
                name: string(record.attributes.first()).unwrap_or_default(),
                description: string(record.attributes.get(1)),
                geodetic_datum: string(record.attributes.get(2)),
                vertical_datum: string(record.attributes.get(3)),
                map_projection: string(record.attributes.get(4)),
                map_zone: string(record.attributes.get(5)),
                map_unit_id,
                map_unit: unit.as_ref().map(|value| value.symbol.clone()),
                map_unit_scale: unit.and_then(|value| value.si_scale),
            })
        });

    if let Some(conversion) = map_conversion {
        return GeoreferencingData {
            has_georeference: true,
            source: Some("mapConversion".to_string()),
            angle_to_grid_north: angle_to_grid_north(&conversion),
            transform_matrix: Some(transform_matrix(&conversion)),
            map_conversion: Some(conversion),
            projected_crs,
        };
    }
    if projected_crs.is_some() {
        return GeoreferencingData {
            has_georeference: true,
            projected_crs,
            ..GeoreferencingData::default()
        };
    }
    if let Some((site_id, longitude, latitude, elevation)) = site_location(model) {
        let conversion = MapConversion {
            express_id: site_id,
            ifc_type: "IfcSiteLocation".to_string(),
            source_crs_id: None,
            target_crs_id: Some(site_id),
            eastings: longitude,
            northings: latitude,
            orthogonal_height: elevation,
            x_axis_abscissa: None,
            x_axis_ordinate: None,
            scale: Some(1.0),
            factor_x: None,
            factor_y: None,
            factor_z: None,
        };
        return GeoreferencingData {
            has_georeference: true,
            source: Some("siteLocation".to_string()),
            transform_matrix: Some(transform_matrix(&conversion)),
            map_conversion: Some(conversion),
            projected_crs: Some(ProjectedCrs {
                express_id: site_id,
                name: "EPSG:4326".to_string(),
                description: Some("Legacy IfcSite geolocation".to_string()),
                geodetic_datum: Some("WGS84".to_string()),
                vertical_datum: None,
                map_projection: Some("Geographic".to_string()),
                map_zone: None,
                map_unit_id: None,
                map_unit: Some("°".to_string()),
                map_unit_scale: None,
            }),
            angle_to_grid_north: None,
        };
    }
    GeoreferencingData::default()
}

fn angle_to_grid_north(conversion: &MapConversion) -> Option<f64> {
    Some(
        conversion
            .x_axis_ordinate?
            .atan2(conversion.x_axis_abscissa?)
            .to_degrees(),
    )
}

fn transform_matrix(conversion: &MapConversion) -> [f64; 16] {
    let scale = conversion.scale.unwrap_or(1.0);
    let angle = match (conversion.x_axis_abscissa, conversion.x_axis_ordinate) {
        (Some(abscissa), Some(ordinate)) => ordinate.atan2(abscissa),
        _ => 0.0,
    };
    let cosine = angle.cos();
    let sine = angle.sin();
    [
        scale * cosine,
        scale * sine,
        0.0,
        0.0,
        -scale * sine,
        scale * cosine,
        0.0,
        0.0,
        0.0,
        0.0,
        scale,
        0.0,
        conversion.eastings,
        conversion.northings,
        conversion.orthogonal_height,
        1.0,
    ]
}

fn site_location(model: &ParsedModel) -> Option<(u32, f64, f64, f64)> {
    for (id, type_name) in &model.entity_types {
        if type_name != "IFCSITE" {
            continue;
        }
        let record = model.records.get(id)?;
        let latitude = compound_angle(record.attributes.get(9))?;
        let longitude = compound_angle(record.attributes.get(10))?;
        let elevation = number(record.attributes.get(11)).unwrap_or(0.0);
        return Some((*id, longitude, latitude, elevation));
    }
    None
}

fn compound_angle(value: Option<&ifx_step::AttributeValue>) -> Option<f64> {
    let values = numbers(value);
    if values.len() < 3 {
        return None;
    }
    let sign = if values.iter().any(|value| value.is_sign_negative()) {
        -1.0
    } else {
        1.0
    };
    let millionths = values.get(3).copied().unwrap_or_default().abs();
    Some(
        sign * (values[0].abs()
            + values[1].abs() / 60.0
            + (values[2].abs() + millionths / 1_000_000.0) / 3600.0),
    )
}
