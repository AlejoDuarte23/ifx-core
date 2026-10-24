use crate::{
    model::ResourcePropertySet,
    parser::{reference, refs, string, ParsedModel},
};
use ifx_step::EntityDecoder;
use std::collections::BTreeMap;

type PropertyIndex = BTreeMap<u32, Vec<u32>>;

pub(crate) fn extract(
    model: &ParsedModel,
    bytes: &[u8],
) -> (
    BTreeMap<u32, ResourcePropertySet>,
    PropertyIndex,
    PropertyIndex,
) {
    let mut sets = BTreeMap::new();
    let mut materials = BTreeMap::new();
    let mut profiles = BTreeMap::new();
    let schema = model.source_schema;
    let mut decoder = EntityDecoder::new(bytes);
    for record in model.records.values() {
        let kind = if schema.is_subtype(&record.ifc_type, "IFCMATERIALPROPERTIES") {
            "material"
        } else if schema.is_subtype(&record.ifc_type, "IFCPROFILEPROPERTIES") {
            "profile"
        } else {
            continue;
        };
        let target = reference(record.get(if kind == "material" {
            "Material"
        } else {
            "ProfileDefinition"
        }));
        let members = record
            .get("ExtendedProperties")
            .or_else(|| record.get("Properties"));
        let ids = refs(members);
        let properties = if members.is_some() {
            ifx_entities::extract_properties(&mut decoder, &ids)
        } else {
            decoder
                .decode_by_id(record.id)
                .map(|entity| {
                    ifx_entities::render_attributes(&entity)
                        .into_iter()
                        .filter(|p| {
                            !matches!(
                                p.name.as_str(),
                                "ProfileName" | "Material" | "ProfileDefinition"
                            )
                        })
                        .collect()
                })
                .unwrap_or_default()
        };
        let name = string(record.get("Name"))
            .or_else(|| string(record.get("ProfileName")))
            .unwrap_or_else(|| record.ifc_type.clone());
        sets.insert(
            record.id,
            ResourcePropertySet {
                express_id: record.id,
                ifc_type: record.ifc_type.clone(),
                resource_kind: kind.into(),
                resource_id: target,
                name,
                description: string(record.get("Description")),
                properties,
            },
        );
        if let Some(id) = target {
            let index: &mut PropertyIndex = if kind == "material" {
                &mut materials
            } else {
                &mut profiles
            };
            index.entry(id).or_default().push(record.id);
        }
    }
    (sets, materials, profiles)
}
