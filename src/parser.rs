use std::{
    collections::{BTreeMap, BTreeSet},
    sync::Arc,
};

use ifx_step::{
    build_entity_index, try_extract_length_unit_scale, AttributeValue, DecodedEntity,
    EntityDecoder, EntityScanner,
};

use crate::Error;

#[derive(Debug, Clone)]
pub(crate) struct EntityRecord {
    pub id: u32,
    pub ifc_type: String,
    pub attributes: Arc<Vec<AttributeValue>>,
    pub attribute_names: &'static [&'static str],
}

impl EntityRecord {
    pub fn get(&self, name: &str) -> Option<&AttributeValue> {
        self.attribute_names
            .iter()
            .position(|n| *n == name)
            .and_then(|i| self.attributes.get(i))
    }
}

#[derive(Debug)]
pub(crate) struct ParsedModel {
    pub schema: Option<String>,
    pub source_schema: ifx_step::schema::SourceSchema,
    pub source_counts: BTreeMap<String, usize>,
    pub duplicate_ids: BTreeSet<u32>,
    pub entity_types: BTreeMap<u32, String>,
    pub records: BTreeMap<u32, EntityRecord>,
    pub project_ids: Vec<u32>,
    pub length_unit_scale: f64,
}

pub(crate) fn supported_schema(bytes: &[u8]) -> Result<ifx_step::schema::SourceSchema, Error> {
    let declared = ifx_step::schema::declared_schema(bytes);
    declared
        .as_deref()
        .and_then(ifx_step::schema::SourceSchema::from_identifier)
        .ok_or_else(|| {
            Error::InvalidIfc(format!(
                "unsupported or missing IFC schema: {}",
                declared.as_deref().unwrap_or("missing")
            ))
        })
}

pub(crate) fn parse_model(bytes: &[u8]) -> Result<ParsedModel, Error> {
    let source_schema = supported_schema(bytes)?;
    let schema = Some(source_schema.family().to_string());

    let mut entity_types = BTreeMap::new();
    let mut source_counts = BTreeMap::new();
    let mut duplicate_ids = BTreeSet::new();
    let mut relevant_ids = Vec::new();
    let mut project_ids = Vec::new();
    let mut scanner = EntityScanner::new(bytes);

    while let Some((id, type_name, _, _)) = scanner.next_entity() {
        let upper = type_name.to_ascii_uppercase();
        if upper == "IFCPROJECT" {
            project_ids.push(id);
        }
        if is_relevant_type(&upper)
            || source_schema.is_subtype(&upper, "IFCTYPEOBJECT")
            || source_schema.is_subtype(&upper, "IFCMATERIALPROPERTIES")
            || source_schema.is_subtype(&upper, "IFCPROFILEPROPERTIES")
        {
            relevant_ids.push(id);
        }
        *source_counts.entry(upper.clone()).or_default() += 1;
        if entity_types.insert(id, upper).is_some() {
            duplicate_ids.insert(id);
        }
    }

    if entity_types.is_empty() {
        return Err(Error::InvalidIfc("no STEP entities found".to_string()));
    }
    if project_ids.is_empty() {
        return Err(Error::InvalidIfc("no IfcProject found".to_string()));
    }

    let index = build_entity_index(bytes);
    let mut decoder = EntityDecoder::with_index(bytes, index);
    let length_unit_scale = project_ids
        .first()
        .and_then(|id| try_extract_length_unit_scale(&mut decoder, *id))
        .or_else(|| {
            project_ids
                .first()
                .and_then(|id| extract_length_unit_scale(&mut decoder, *id))
        })
        .unwrap_or(1.0);

    let mut records = BTreeMap::new();
    for id in relevant_ids {
        let entity = decoder
            .decode_by_id(id)
            .map_err(|error| Error::ParseEntity {
                express_id: id,
                message: error.to_string(),
            })?;
        records.insert(id, record_from_entity(entity));
    }

    // Decode only the short placement chain needed for the storey-elevation
    // fallback. Parsing every CartesianPoint would pull the model's complete
    // geometry coordinate population into this relationship-only library.
    let storey_ids: Vec<u32> = entity_types
        .iter()
        .filter_map(|(id, type_name)| (type_name == "IFCBUILDINGSTOREY").then_some(*id))
        .collect();
    for storey_id in storey_ids {
        let placement_id = records
            .get(&storey_id)
            .and_then(|record| reference(record.attributes.get(5)));
        let Some(placement_id) = placement_id else {
            continue;
        };
        decode_and_insert(&mut decoder, &mut records, placement_id)?;
        let axis_id = records
            .get(&placement_id)
            .and_then(|record| reference(record.attributes.get(1)));
        let Some(axis_id) = axis_id else { continue };
        decode_and_insert(&mut decoder, &mut records, axis_id)?;
        let location_id = records
            .get(&axis_id)
            .and_then(|record| reference(record.attributes.first()));
        let Some(location_id) = location_id else {
            continue;
        };
        decode_and_insert(&mut decoder, &mut records, location_id)?;
    }

    Ok(ParsedModel {
        schema,
        source_schema,
        source_counts,
        duplicate_ids,
        entity_types,
        records,
        project_ids,
        length_unit_scale,
    })
}

fn extract_length_unit_scale(decoder: &mut EntityDecoder<'_>, project_id: u32) -> Option<f64> {
    let project = decoder.decode_by_id(project_id).ok()?;
    let assignment_id = reference(project.attributes.get(8))?;
    let assignment = decoder.decode_by_id(assignment_id).ok()?;
    for unit_id in refs(assignment.attributes.first()) {
        if let Some(scale) = length_unit_scale(decoder, unit_id, &mut BTreeSet::new()) {
            return Some(scale);
        }
    }
    None
}

fn length_unit_scale(
    decoder: &mut EntityDecoder<'_>,
    unit_id: u32,
    visited: &mut BTreeSet<u32>,
) -> Option<f64> {
    if !visited.insert(unit_id) {
        return None;
    }
    let unit = decoder.decode_by_id(unit_id).ok()?;
    if !enum_is(unit.attributes.get(1), "LENGTHUNIT") {
        return None;
    }

    match format!("{:?}", unit.ifc_type).to_ascii_uppercase().as_str() {
        "IFCSIUNIT" if enum_is(unit.attributes.get(3), "METRE") => {
            Some(si_prefix_scale(unit.attributes.get(2)))
        }
        "IFCCONVERSIONBASEDUNIT" => {
            let factor_id = reference(unit.attributes.get(3))?;
            let factor = decoder.decode_by_id(factor_id).ok()?;
            let value = number(factor.attributes.first())?;
            let component_id = reference(factor.attributes.get(1))?;
            Some(value * length_unit_scale(decoder, component_id, visited)?)
        }
        _ => None,
    }
}

fn enum_is(value: Option<&AttributeValue>, expected: &str) -> bool {
    matches!(value, Some(AttributeValue::Enum(actual)) if actual.eq_ignore_ascii_case(expected))
}

fn si_prefix_scale(value: Option<&AttributeValue>) -> f64 {
    let Some(AttributeValue::Enum(prefix)) = value else {
        return 1.0;
    };
    match prefix.to_ascii_uppercase().as_str() {
        "EXA" => 1e18,
        "PETA" => 1e15,
        "TERA" => 1e12,
        "GIGA" => 1e9,
        "MEGA" => 1e6,
        "KILO" => 1e3,
        "HECTO" => 1e2,
        "DECA" => 1e1,
        "DECI" => 1e-1,
        "CENTI" => 1e-2,
        "MILLI" => 1e-3,
        "MICRO" => 1e-6,
        "NANO" => 1e-9,
        "PICO" => 1e-12,
        "FEMTO" => 1e-15,
        "ATTO" => 1e-18,
        _ => 1.0,
    }
}

fn decode_and_insert(
    decoder: &mut EntityDecoder<'_>,
    records: &mut BTreeMap<u32, EntityRecord>,
    express_id: u32,
) -> Result<(), Error> {
    if records.contains_key(&express_id) {
        return Ok(());
    }
    let entity = decoder
        .decode_by_id(express_id)
        .map_err(|error| Error::ParseEntity {
            express_id,
            message: error.to_string(),
        })?;
    records.insert(express_id, record_from_entity(entity));
    Ok(())
}

fn record_from_entity(entity: DecodedEntity) -> EntityRecord {
    EntityRecord {
        id: entity.id,
        ifc_type: entity.source_name().to_string(),
        attribute_names: entity.attribute_names(),
        attributes: entity.attributes,
    }
}

fn is_relevant_type(type_upper: &str) -> bool {
    is_spatial_type(type_upper)
        || matches!(
            type_upper,
            "IFCRELAGGREGATES"
                | "IFCRELNESTS"
                | "IFCRELCONTAINEDINSPATIALSTRUCTURE"
                | "IFCRELREFERENCEDINSPATIALSTRUCTURE"
                | "IFCRELDEFINESBYTYPE"
                | "IFCRELDEFINESBYPROPERTIES"
                | "IFCRELSERVICESBUILDINGS"
                | "IFCRELASSOCIATESMATERIAL"
                | "IFCRELASSOCIATESCLASSIFICATION"
                | "IFCRELASSOCIATESDOCUMENT"
                | "IFCCLASSIFICATION"
                | "IFCCLASSIFICATIONREFERENCE"
                | "IFCDOCUMENTINFORMATION"
                | "IFCDOCUMENTREFERENCE"
                | "IFCGROUP"
                | "IFCZONE"
                | "IFCSYSTEM"
                | "IFCDISTRIBUTIONSYSTEM"
                | "IFCBUILDINGSYSTEM"
                | "IFCBUILTSYSTEM"
                | "IFCDISTRIBUTIONCIRCUIT"
                | "IFCELECTRICALCIRCUIT"
                | "IFCCALENDARDATE"
                | "IFCDATEANDTIME"
                | "IFCLOCALTIME"
                | "IFCDOCUMENTELECTRONICFORMAT"
                | "IFCASSET"
                | "IFCINVENTORY"
                | "IFCSTRUCTURALLOADGROUP"
                | "IFCSTRUCTURALLOADCASE"
                | "IFCSTRUCTURALRESULTGROUP"
                | "IFCSTRUCTURALANALYSISMODEL"
                | "IFCRELVOIDSELEMENT"
                | "IFCRELFILLSELEMENT"
                | "IFCRELCONNECTSELEMENTS"
                | "IFCRELCONNECTSPATHELEMENTS"
                | "IFCRELCONNECTSPORTTOELEMENT"
                | "IFCRELCONNECTSPORTS"
                | "IFCRELSPACEBOUNDARY"
                | "IFCRELSPACEBOUNDARY1STLEVEL"
                | "IFCRELSPACEBOUNDARY2NDLEVEL"
                | "IFCDISTRIBUTIONPORT"
                | "IFCMAPCONVERSION"
                | "IFCMAPCONVERSIONSCALED"
                | "IFCPROJECTEDCRS"
                | "IFCRELASSIGNSTOGROUP"
                | "IFCRELASSIGNSTOGROUPBYFACTOR"
                | "IFCRELASSIGNSTOPRODUCT"
                | "IFCMATERIAL"
                | "IFCMATERIALLAYER"
                | "IFCMATERIALLAYERSET"
                | "IFCMATERIALLAYERSETUSAGE"
                | "IFCMATERIALPROFILE"
                | "IFCMATERIALPROFILESET"
                | "IFCMATERIALPROFILESETUSAGE"
                | "IFCMATERIALCONSTITUENT"
                | "IFCMATERIALCONSTITUENTSET"
                | "IFCMATERIALLIST"
                | "IFCUNITASSIGNMENT"
                | "IFCSIUNIT"
                | "IFCCONVERSIONBASEDUNIT"
                | "IFCCONVERSIONBASEDUNITWITHOFFSET"
                | "IFCDERIVEDUNIT"
                | "IFCDERIVEDUNITELEMENT"
                | "IFCMONETARYUNIT"
                | "IFCCONTEXTDEPENDENTUNIT"
                | "IFCMEASUREWITHUNIT"
        )
}

pub(crate) fn is_spatial_type(type_upper: &str) -> bool {
    matches!(
        type_upper,
        "IFCPROJECT"
            | "IFCSITE"
            | "IFCBUILDING"
            | "IFCBUILDINGSTOREY"
            | "IFCSPACE"
            | "IFCSPATIALZONE"
            | "IFCFACILITY"
            | "IFCFACILITYPART"
            | "IFCFACILITYPARTCOMMON"
            | "IFCBRIDGE"
            | "IFCBRIDGEPART"
            | "IFCROAD"
            | "IFCROADPART"
            | "IFCRAILWAY"
            | "IFCRAILWAYPART"
            | "IFCMARINEFACILITY"
            | "IFCMARINEPART"
    )
}

pub(crate) fn refs(value: Option<&AttributeValue>) -> Vec<u32> {
    match value {
        Some(AttributeValue::EntityRef(id)) => vec![*id],
        Some(AttributeValue::List(values)) => values
            .iter()
            .filter_map(AttributeValue::as_entity_ref)
            .collect(),
        _ => Vec::new(),
    }
}

pub(crate) fn reference(value: Option<&AttributeValue>) -> Option<u32> {
    value.and_then(AttributeValue::as_entity_ref)
}

pub(crate) fn string(value: Option<&AttributeValue>) -> Option<String> {
    value
        .and_then(AttributeValue::as_string)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

pub(crate) fn strings(value: Option<&AttributeValue>) -> Vec<String> {
    match value {
        Some(AttributeValue::List(values)) => values
            .iter()
            .filter_map(|value| string(Some(value)))
            .collect(),
        _ => string(value).into_iter().collect(),
    }
}

pub(crate) fn number(value: Option<&AttributeValue>) -> Option<f64> {
    match value {
        Some(AttributeValue::Float(value)) => Some(*value),
        Some(AttributeValue::Integer(value)) => Some(*value as f64),
        Some(AttributeValue::List(values)) if values.len() >= 2 => number(values.get(1)),
        _ => None,
    }
}

pub(crate) fn integers(value: Option<&AttributeValue>) -> Vec<i64> {
    match value {
        Some(AttributeValue::Integer(value)) => vec![*value],
        Some(AttributeValue::List(values)) => values
            .iter()
            .filter_map(|item| match item {
                AttributeValue::Integer(value) => Some(*value),
                _ => None,
            })
            .collect(),
        _ => Vec::new(),
    }
}

pub(crate) fn numbers(value: Option<&AttributeValue>) -> Vec<f64> {
    match value {
        Some(AttributeValue::Float(value)) => vec![*value],
        Some(AttributeValue::Integer(value)) => vec![*value as f64],
        Some(AttributeValue::List(values)) => {
            values.iter().flat_map(|item| numbers(Some(item))).collect()
        }
        _ => Vec::new(),
    }
}

pub(crate) fn boolean(value: Option<&AttributeValue>) -> Option<bool> {
    match value {
        Some(AttributeValue::Enum(value)) => match value.to_ascii_uppercase().as_str() {
            "T" | "TRUE" => Some(true),
            "F" | "FALSE" => Some(false),
            _ => None,
        },
        _ => None,
    }
}

pub(crate) fn enumeration(value: Option<&AttributeValue>) -> Option<String> {
    match value {
        Some(AttributeValue::Enum(value)) => Some(value.trim_matches('.').to_ascii_uppercase()),
        _ => string(value).map(|value| value.trim_matches('.').to_ascii_uppercase()),
    }
}
