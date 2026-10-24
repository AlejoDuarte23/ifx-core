use std::collections::BTreeMap;

use crate::{
    model::{GroupDefinition, GroupsData},
    parser::{enumeration, string, ParsedModel},
    relationships::Relations,
};

pub(crate) fn build_groups(model: &ParsedModel, relations: &Relations) -> GroupsData {
    let definitions = model
        .entity_types
        .iter()
        .filter_map(|(id, type_name)| {
            if !is_group_type(type_name) {
                return None;
            }
            let record = model.records.get(id)?;
            Some((
                *id,
                GroupDefinition {
                    express_id: *id,
                    ifc_type: record.ifc_type.clone(),
                    global_id: string(record.attributes.first()),
                    name: string(record.attributes.get(2)),
                    description: string(record.attributes.get(3)),
                    object_type: string(record.attributes.get(4)),
                    long_name: string(record.get("LongName")),
                    predefined_type: enumeration(record.get("PredefinedType")),
                },
            ))
        })
        .collect();

    let mut groups_by_object = BTreeMap::new();
    let mut members_by_group = BTreeMap::new();
    for membership in &relations.group_memberships {
        groups_by_object
            .entry(membership.object_id)
            .or_insert_with(Vec::new)
            .push(membership.clone());
        members_by_group
            .entry(membership.group_id)
            .or_insert_with(Vec::new)
            .push(membership.clone());
    }

    let mut products_by_object: BTreeMap<u32, Vec<u32>> = BTreeMap::new();
    let mut objects_by_product: BTreeMap<u32, Vec<u32>> = BTreeMap::new();
    for assignment in &relations.product_assignments {
        products_by_object
            .entry(assignment.object_id)
            .or_default()
            .push(assignment.product_id);
        objects_by_product
            .entry(assignment.product_id)
            .or_default()
            .push(assignment.object_id);
    }
    for values in products_by_object.values_mut() {
        values.sort_unstable();
        values.dedup();
    }
    for values in objects_by_product.values_mut() {
        values.sort_unstable();
        values.dedup();
    }

    GroupsData {
        definitions,
        memberships: relations.group_memberships.clone(),
        groups_by_object,
        members_by_group,
        product_assignments: relations.product_assignments.clone(),
        products_by_object,
        objects_by_product,
    }
}

fn is_group_type(type_name: &str) -> bool {
    matches!(
        type_name,
        "IFCGROUP"
            | "IFCZONE"
            | "IFCSYSTEM"
            | "IFCDISTRIBUTIONSYSTEM"
            | "IFCDISTRIBUTIONCIRCUIT"
            | "IFCELECTRICALCIRCUIT"
            | "IFCBUILDINGSYSTEM"
            | "IFCBUILTSYSTEM"
            | "IFCASSET"
            | "IFCINVENTORY"
            | "IFCSTRUCTURALLOADGROUP"
            | "IFCSTRUCTURALLOADCASE"
            | "IFCSTRUCTURALRESULTGROUP"
            | "IFCSTRUCTURALANALYSISMODEL"
    )
}
