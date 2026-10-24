use std::collections::{BTreeMap, BTreeSet};

use crate::{
    model::{
        ClassificationReference, ClassificationSystem, ClassificationsData,
        ElementClassificationAssignment,
    },
    parser::{reference, string, strings, ParsedModel},
    relationships::Relations,
};

pub(crate) fn build_classifications(
    model: &ParsedModel,
    relations: &Relations,
) -> ClassificationsData {
    let systems: BTreeMap<u32, ClassificationSystem> = model
        .entity_types
        .iter()
        .filter_map(|(id, type_name)| {
            (type_name == "IFCCLASSIFICATION").then(|| {
                let record = model.records.get(id)?;
                Some((
                    *id,
                    ClassificationSystem {
                        express_id: *id,
                        source: string(record.attributes.first()),
                        edition: string(record.attributes.get(1)),
                        edition_date: crate::documents::document_date(
                            model,
                            record.get("EditionDate"),
                        ),
                        name: string(record.attributes.get(3)).unwrap_or_default(),
                        description: string(record.attributes.get(4)),
                        location: string(record.attributes.get(5)),
                        reference_tokens: strings(record.attributes.get(6)),
                    },
                ))
            })?
        })
        .collect();

    let mut references: BTreeMap<u32, ClassificationReference> = model
        .entity_types
        .iter()
        .filter_map(|(id, type_name)| {
            (type_name == "IFCCLASSIFICATIONREFERENCE").then(|| {
                let record = model.records.get(id)?;
                Some((
                    *id,
                    ClassificationReference {
                        express_id: *id,
                        location: string(record.attributes.first()),
                        identification: string(record.attributes.get(1)),
                        name: string(record.attributes.get(2)),
                        referenced_source_id: reference(record.attributes.get(3)),
                        description: string(record.attributes.get(4)),
                        sort: string(record.attributes.get(5)),
                        system_id: None,
                        system_name: None,
                        path: Vec::new(),
                    },
                ))
            })?
        })
        .collect();

    let reference_ids: Vec<u32> = references.keys().copied().collect();
    for reference_id in reference_ids {
        let (system_id, path) = classification_path(reference_id, &references, &systems);
        if let Some(item) = references.get_mut(&reference_id) {
            item.system_id = system_id;
            item.system_name =
                system_id.and_then(|id| systems.get(&id).map(|system| system.name.clone()));
            item.path = path;
        }
    }

    let mut own: BTreeMap<u32, Vec<(u32, u32)>> = BTreeMap::new();
    for association in &relations.classification_associations {
        for object_id in &association.related_objects {
            own.entry(*object_id)
                .or_default()
                .push((association.relationship_id, association.classification_id));
        }
    }
    for assignments in own.values_mut() {
        assignments.sort_unstable();
        assignments.dedup();
    }

    let candidate_ids: BTreeSet<u32> = own
        .keys()
        .filter(|id| !is_type_like(model.entity_types.get(id).map(String::as_str)))
        .copied()
        .chain(relations.defines_type.keys().copied())
        .collect();
    let mut element_classifications = BTreeMap::new();
    for entity_id in candidate_ids {
        let mut assignments = Vec::new();
        let mut seen = BTreeSet::new();
        for (_, classification_id) in own.get(&entity_id).into_iter().flatten() {
            if seen.insert(*classification_id) {
                assignments.push(ElementClassificationAssignment {
                    classification_id: *classification_id,
                    inherited_from_type: None,
                });
            }
        }
        for (_, type_id) in relations.defines_type.get(&entity_id).into_iter().flatten() {
            for (_, classification_id) in own.get(type_id).into_iter().flatten() {
                if seen.insert(*classification_id) {
                    assignments.push(ElementClassificationAssignment {
                        classification_id: *classification_id,
                        inherited_from_type: Some(*type_id),
                    });
                }
            }
        }
        if !assignments.is_empty() {
            element_classifications.insert(entity_id, assignments);
        }
    }

    ClassificationsData {
        systems,
        references,
        associations: relations.classification_associations.clone(),
        element_classifications,
    }
}

fn classification_path(
    reference_id: u32,
    references: &BTreeMap<u32, ClassificationReference>,
    systems: &BTreeMap<u32, ClassificationSystem>,
) -> (Option<u32>, Vec<String>) {
    let mut path = Vec::new();
    let mut current_id = Some(reference_id);
    let mut visited = BTreeSet::new();
    while let Some(id) = current_id {
        if !visited.insert(id) {
            break;
        }
        if systems.contains_key(&id) {
            path.reverse();
            return (Some(id), path);
        }
        let Some(reference) = references.get(&id) else {
            break;
        };
        if let Some(label) = reference
            .identification
            .as_ref()
            .or(reference.name.as_ref())
        {
            path.push(label.clone());
        }
        current_id = reference.referenced_source_id;
    }
    path.reverse();
    (None, path)
}

fn is_type_like(type_name: Option<&str>) -> bool {
    type_name.is_some_and(|value| value.ends_with("TYPE") || value.ends_with("STYLE"))
}
