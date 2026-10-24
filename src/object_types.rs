use crate::{
    model::{ObjectTypeDefinition, ObjectTypesData},
    parser::{string, ParsedModel},
    relationships::Relations,
};
use ifx_step::{DecodedEntity, IfcType};

pub(crate) fn extract(model: &ParsedModel, relations: &Relations) -> ObjectTypesData {
    let mut data = ObjectTypesData::default();
    for record in model.records.values() {
        if !model
            .source_schema
            .is_subtype(&record.ifc_type, "IFCTYPEOBJECT")
        {
            continue;
        }
        let entity = DecodedEntity {
            id: record.id,
            ifc_type: IfcType::from_str(&record.ifc_type),
            attributes: record.attributes.clone(),
            source_definition: model.source_schema.entity(&record.ifc_type),
        };
        data.definitions.insert(
            record.id,
            ObjectTypeDefinition {
                express_id: record.id,
                ifc_type: record.ifc_type.clone(),
                global_id: string(record.get("GlobalId")),
                name: string(record.get("Name")),
                description: string(record.get("Description")),
                attributes: ifx_entities::render_attributes(&entity),
            },
        );
    }
    for (element_id, assignments) in &relations.defines_type {
        let mut ids = Vec::new();
        for (_, type_id) in assignments {
            if data.definitions.contains_key(type_id) && !ids.contains(type_id) {
                ids.push(*type_id);
            }
        }
        if !ids.is_empty() {
            data.types_by_element.insert(*element_id, ids);
        }
    }
    data
}
