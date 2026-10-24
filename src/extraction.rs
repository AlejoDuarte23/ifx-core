// SPDX-License-Identifier: MPL-2.0
use crate::{analyze_ifc, Error, ModelData};
use ifx_entities::{build_export_model_with_options, ExportModel, ModelOptions};
use ifx_processing::{
    build_geometry_data_export, process_geometry_filtered_with_quality, GeometryDataExport,
    OpeningFilterMode, TessellationQuality,
};
use serde::Serialize;

#[derive(Serialize)]
pub struct Extraction {
    pub geometry: GeometryDataExport,
    pub entities: ExportModel,
    pub model: ModelData,
}

/// Geometry uses IFC Z-up world metres. Entity values keep source units.
pub fn extract(bytes: &[u8], quality: &str) -> Result<Extraction, Error> {
    let mut model = analyze_ifc(bytes)?;
    let quality = TessellationQuality::parse_label(quality)
        .ok_or_else(|| Error::InvalidIfc(format!("unknown geometry quality: {quality}")))?;
    let result = process_geometry_filtered_with_quality(bytes, OpeningFilterMode::Default, quality);
    let rotation = if result.mesh_coordinate_space.as_deref() == Some("site_local") {
        result.site_transform.as_deref()
    } else {
        None
    };
    let geometry = build_geometry_data_export(
        &result.meshes,
        result.metadata.coordinate_info.origin_shift,
        rotation,
    );
    let options = ModelOptions::default()
        .with_placements(true)
        .with_inherit_type_properties(true)
        .with_attributes(true);
    let entities = build_export_model_with_options(bytes, &options);
    crate::coverage::complete(&mut model, &entities, &geometry, bytes);
    Ok(Extraction {
        geometry,
        entities,
        model,
    })
}
