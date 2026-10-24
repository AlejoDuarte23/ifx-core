use std::collections::BTreeSet;

use super::props::render_value;
use super::{PropValue, PropertyAtom, PropertyDetails};
use ifx_step::{AttributeValue, DecodedEntity, EntityDecoder};

const MAX_DEPTH: usize = 16;
const MAX_NODES: usize = 4096;
const MAX_VALUES: usize = 4096;

pub fn extract_properties(decoder: &mut EntityDecoder, ids: &[u32]) -> Vec<PropValue> {
    let mut state = ReadState {
        remaining: MAX_NODES,
        path: BTreeSet::new(),
    };
    read_children(decoder, ids, &mut state, 0)
}

struct ReadState {
    remaining: usize,
    path: BTreeSet<u32>,
}

fn read_children(
    decoder: &mut EntityDecoder,
    ids: &[u32],
    state: &mut ReadState,
    depth: usize,
) -> Vec<PropValue> {
    let mut values = Vec::new();
    for (position, id) in ids.iter().enumerate() {
        if state.remaining == 0 {
            values.push(PropValue {
                name: "Remaining properties".into(),
                value: (ids.len() - position).to_string(),
                value_type: "UNAVAILABLE".into(),
                issue: Some("node_limit".into()),
                ..PropValue::default()
            });
            break;
        }
        if let Some(value) = read_property(decoder, *id, state, depth) {
            values.push(value);
        }
    }
    values
}

fn atom(value: Option<&AttributeValue>) -> Option<PropertyAtom> {
    let (value, value_type) = render_value(value?)?;
    Some(PropertyAtom { value, value_type })
}

fn atoms(value: Option<&AttributeValue>) -> (Vec<PropertyAtom>, Option<String>) {
    let Some(items) = value.and_then(AttributeValue::as_list) else {
        return (Vec::new(), None);
    };
    let values: Vec<_> = items
        .iter()
        .take(MAX_VALUES)
        .filter_map(|v| atom(Some(v)))
        .collect();
    let issue = if items.len() > MAX_VALUES {
        Some("value_limit".into())
    } else if values.len() != items.len() {
        Some("invalid_value".into())
    } else {
        None
    };
    (values, issue)
}

fn display(values: &[PropertyAtom]) -> String {
    values
        .iter()
        .map(|v| v.value.as_str())
        .collect::<Vec<_>>()
        .join(", ")
}

fn read_property(
    decoder: &mut EntityDecoder,
    id: u32,
    state: &mut ReadState,
    depth: usize,
) -> Option<PropValue> {
    state.remaining = state.remaining.saturating_sub(1);
    let entity = match decoder.decode_by_id(id) {
        Ok(entity) => entity,
        Err(_) => {
            return Some(PropValue {
                name: format!("#{id}"),
                value: "Unavailable".into(),
                value_type: "UNAVAILABLE".into(),
                issue: Some("missing_property".into()),
                ..PropValue::default()
            })
        }
    };
    let mut value = PropValue {
        name: entity
            .get_string(0)
            .filter(|v| !v.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| format!("#{id}")),
        value_type: entity.source_name().to_string(),
        unit_id: entity
            .get_named("Unit")
            .and_then(AttributeValue::as_entity_ref),
        ..PropValue::default()
    };
    if state.path.contains(&id) {
        value.value = "Unavailable".into();
        value.issue = Some("cycle".into());
        return Some(value);
    }
    if depth >= MAX_DEPTH {
        value.value = "Unavailable".into();
        value.issue = Some("depth_limit".into());
        return Some(value);
    }
    state.path.insert(id);
    let result = read_value(decoder, &entity, state, depth, value);
    state.path.remove(&id);
    result
}

fn read_value(
    decoder: &mut EntityDecoder,
    entity: &DecodedEntity,
    state: &mut ReadState,
    depth: usize,
    mut result: PropValue,
) -> Option<PropValue> {
    match entity.source_name() {
        "IfcPropertySingleValue" => {
            let raw = entity.get_named("NominalValue")?;
            if raw.is_null() {
                return None;
            }
            if let Some(value) = atom(Some(raw)) {
                result.value = value.value;
                result.value_type = value.value_type;
            } else {
                result.value = "Unavailable".into();
                result.issue = Some("unsupported_value".into());
            }
        }
        "IfcPropertyEnumeratedValue" | "IfcPropertyListValue" => {
            let enumerated = entity.source_name() == "IfcPropertyEnumeratedValue";
            let input = entity.get_named(if enumerated {
                "EnumerationValues"
            } else {
                "ListValues"
            })?;
            if input.is_null() {
                return None;
            }
            let (values, issue) = atoms(Some(input));
            result.issue = issue;
            if enumerated {
                if let Some(id) = entity
                    .get_named("EnumerationReference")
                    .and_then(AttributeValue::as_entity_ref)
                {
                    match decoder.decode_by_id(id) {
                        Ok(enumeration) => {
                            result.unit_id = enumeration
                                .get_named("Unit")
                                .and_then(AttributeValue::as_entity_ref)
                        }
                        Err(_) => result.issue = Some("missing_reference".into()),
                    }
                }
            }
            result.value = display(&values);
            result.details = Some(if enumerated {
                PropertyDetails::Enumerated {
                    values,
                    enumeration_id: entity
                        .get_named("EnumerationReference")
                        .and_then(AttributeValue::as_entity_ref),
                }
            } else {
                PropertyDetails::List { values }
            });
        }
        "IfcPropertyBoundedValue" => {
            let lower = atom(entity.get_named("LowerBoundValue"));
            let upper = atom(entity.get_named("UpperBoundValue"));
            let set_point = atom(entity.get_named("SetPointValue"));
            if lower.is_none() && upper.is_none() && set_point.is_none() {
                return None;
            }
            fn text(value: &Option<PropertyAtom>) -> &str {
                value.as_ref().map_or("", |v| v.value.as_str())
            }
            result.value = format!("{} .. {}", text(&lower), text(&upper));
            if let Some(point) = &set_point {
                result.value.push_str(&format!(" (target {})", point.value));
            }
            result.details = Some(PropertyDetails::Bounded {
                lower,
                upper,
                set_point,
            });
        }
        "IfcPropertyTableValue" => {
            let (defining, first_issue) = atoms(entity.get_named("DefiningValues"));
            let (defined, second_issue) = atoms(entity.get_named("DefinedValues"));
            result.issue = first_issue
                .or(second_issue)
                .or_else(|| (defining.len() != defined.len()).then(|| "unequal_columns".into()));
            result.value = defining
                .iter()
                .zip(&defined)
                .map(|(a, b)| format!("{} → {}", a.value, b.value))
                .collect::<Vec<_>>()
                .join("; ");
            result.details = Some(PropertyDetails::Table {
                defining,
                defined,
                expression: entity
                    .get_named("Expression")
                    .and_then(AttributeValue::as_string)
                    .map(str::to_string),
                defining_unit_id: entity
                    .get_named("DefiningUnit")
                    .and_then(AttributeValue::as_entity_ref),
                defined_unit_id: entity
                    .get_named("DefinedUnit")
                    .and_then(AttributeValue::as_entity_ref),
                interpolation: entity
                    .get_named("CurveInterpolation")
                    .and_then(AttributeValue::as_enum)
                    .map(str::to_string),
            });
        }
        "IfcPropertyReferenceValue" => {
            let id = entity
                .get_named("PropertyReference")
                .and_then(AttributeValue::as_entity_ref)?;
            let target = decoder.decode_by_id(id).ok();
            let name = target
                .as_ref()
                .and_then(|e| e.get_named("Name").and_then(AttributeValue::as_string))
                .map(str::to_string);
            let ifc_type = target.as_ref().map(|e| e.source_name().to_string());
            result.value = name.clone().unwrap_or_else(|| format!("#{id}"));
            if target.is_none() {
                result.issue = Some("missing_reference".into());
            }
            result.details = Some(PropertyDetails::Reference {
                express_id: id,
                ifc_type,
                name,
            });
        }
        "IfcComplexProperty" => {
            let ids: Vec<_> = entity
                .get_named("HasProperties")
                .and_then(AttributeValue::as_list)
                .unwrap_or_default()
                .iter()
                .filter_map(AttributeValue::as_entity_ref)
                .collect();
            let properties = read_children(decoder, &ids, state, depth + 1);
            result.value = properties
                .iter()
                .map(|p| format!("{}: {}", p.name, p.value))
                .collect::<Vec<_>>()
                .join("; ")
                .chars()
                .take(4096)
                .collect();
            result.details = Some(PropertyDetails::Complex {
                usage_name: entity
                    .get_named("UsageName")
                    .and_then(AttributeValue::as_string)
                    .map(str::to_string),
                properties,
            });
        }
        _ => {
            result.value = "Unavailable".into();
            result.issue = Some("unsupported_property".into());
        }
    }
    Some(result)
}
