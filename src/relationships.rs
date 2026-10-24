use std::collections::BTreeMap;

use crate::{
    model::{
        ClassificationAssociation, DocumentAssociation, FillRelationship, GroupMembership,
        MaterialAssociation, ProductAssignment, RelationshipData, RelationshipEdge,
        VoidRelationship,
    },
    parser::{number, reference, refs, EntityRecord, ParsedModel},
};

#[derive(Debug, Clone, Default)]
pub(crate) struct Relations {
    pub edges: RelationshipData,
    pub aggregates: BTreeMap<u32, Vec<u32>>,
    pub contains: BTreeMap<u32, Vec<u32>>,
    pub references: BTreeMap<u32, Vec<u32>>,
    pub defines_type: BTreeMap<u32, Vec<(u32, u32)>>,
    pub material_associations: Vec<MaterialAssociation>,
    pub classification_associations: Vec<ClassificationAssociation>,
    pub document_associations: Vec<DocumentAssociation>,
    pub group_memberships: Vec<GroupMembership>,
    pub product_assignments: Vec<ProductAssignment>,
    pub voids: Vec<VoidRelationship>,
    pub fills: Vec<FillRelationship>,
}

pub(crate) fn extract_relations(model: &ParsedModel) -> Relations {
    let mut out = Relations::default();

    for record in model.records.values() {
        let upper = model
            .entity_types
            .get(&record.id)
            .map(String::as_str)
            .unwrap_or_default();
        match upper {
            "IFCRELAGGREGATES" | "IFCRELNESTS" => {
                add_single_to_many(record, upper, 4, 5, &mut out.aggregates, &mut out.edges)
            }
            "IFCRELCONTAINEDINSPATIALSTRUCTURE" => {
                add_many_to_single(record, upper, 4, 5, &mut out.contains, &mut out.edges)
            }
            "IFCRELREFERENCEDINSPATIALSTRUCTURE" => {
                add_many_to_single(record, upper, 4, 5, &mut out.references, &mut out.edges)
            }
            "IFCRELDEFINESBYTYPE" => {
                let targets = refs(record.attributes.get(4));
                if let Some(type_id) = reference(record.attributes.get(5)) {
                    for target in targets {
                        out.defines_type
                            .entry(target)
                            .or_default()
                            .push((record.id, type_id));
                        out.edges.edges.push(edge(record, upper, type_id, target));
                    }
                }
            }
            "IFCRELDEFINESBYPROPERTIES" => add_many_to_many(record, upper, 4, 5, &mut out.edges),
            "IFCRELSERVICESBUILDINGS" => {
                if let Some(system_id) = reference(record.get("RelatingSystem")) {
                    for building_id in refs(record.get("RelatedBuildings")) {
                        out.edges
                            .edges
                            .push(edge(record, upper, system_id, building_id));
                    }
                }
            }
            "IFCRELASSOCIATESDOCUMENT" => {
                let related_objects = refs(record.attributes.get(4));
                if let Some(document_id) = reference(record.attributes.get(5)) {
                    for target in &related_objects {
                        out.edges
                            .edges
                            .push(edge(record, upper, document_id, *target));
                    }
                    out.document_associations.push(DocumentAssociation {
                        relationship_id: record.id,
                        document_id,
                        related_objects,
                    });
                }
            }
            "IFCRELASSOCIATESCLASSIFICATION" => {
                let related_objects = refs(record.attributes.get(4));
                if let Some(classification_id) = reference(record.attributes.get(5)) {
                    for target in &related_objects {
                        out.edges
                            .edges
                            .push(edge(record, upper, classification_id, *target));
                    }
                    out.classification_associations
                        .push(ClassificationAssociation {
                            relationship_id: record.id,
                            classification_id,
                            related_objects,
                        });
                }
            }
            "IFCRELASSOCIATESMATERIAL" => {
                let related_objects = refs(record.attributes.get(4));
                if let Some(material_id) = reference(record.attributes.get(5)) {
                    for target in &related_objects {
                        out.edges
                            .edges
                            .push(edge(record, upper, material_id, *target));
                    }
                    out.material_associations.push(MaterialAssociation {
                        relationship_id: record.id,
                        relating_material_id: material_id,
                        related_objects,
                    });
                }
            }
            "IFCRELVOIDSELEMENT" => {
                if let (Some(element_id), Some(opening_id)) = (
                    reference(record.attributes.get(4)),
                    reference(record.attributes.get(5)),
                ) {
                    out.edges
                        .edges
                        .push(edge(record, upper, element_id, opening_id));
                    out.voids.push(VoidRelationship {
                        relationship_id: record.id,
                        element_id,
                        opening_id,
                    });
                }
            }
            "IFCRELFILLSELEMENT" => {
                if let (Some(opening_id), Some(filling_id)) = (
                    reference(record.attributes.get(4)),
                    reference(record.attributes.get(5)),
                ) {
                    out.edges
                        .edges
                        .push(edge(record, upper, opening_id, filling_id));
                    out.fills.push(FillRelationship {
                        relationship_id: record.id,
                        opening_id,
                        filling_id,
                    });
                }
            }
            "IFCRELASSIGNSTOGROUP" | "IFCRELASSIGNSTOGROUPBYFACTOR" => {
                let objects = refs(record.attributes.get(4));
                if let Some(group_id) = reference(record.attributes.get(6)) {
                    let factor = (upper == "IFCRELASSIGNSTOGROUPBYFACTOR")
                        .then(|| number(record.attributes.get(7)))
                        .flatten();
                    for object_id in objects {
                        out.edges
                            .edges
                            .push(edge(record, upper, group_id, object_id));
                        out.group_memberships.push(GroupMembership {
                            relationship_id: record.id,
                            group_id,
                            object_id,
                            factor,
                        });
                    }
                }
            }
            "IFCRELASSIGNSTOPRODUCT" => {
                let objects = refs(record.attributes.get(4));
                if let Some(product_id) = reference(record.attributes.get(6)) {
                    for object_id in objects {
                        out.edges
                            .edges
                            .push(edge(record, upper, product_id, object_id));
                        out.product_assignments.push(ProductAssignment {
                            relationship_id: record.id,
                            product_id,
                            object_id,
                        });
                    }
                }
            }
            "IFCRELCONNECTSELEMENTS" | "IFCRELCONNECTSPATHELEMENTS" => {
                add_single_to_single(record, upper, 5, 6, &mut out.edges)
            }
            "IFCRELCONNECTSPORTTOELEMENT"
            | "IFCRELCONNECTSPORTS"
            | "IFCRELSPACEBOUNDARY"
            | "IFCRELSPACEBOUNDARY1STLEVEL"
            | "IFCRELSPACEBOUNDARY2NDLEVEL" => {
                add_single_to_single(record, upper, 4, 5, &mut out.edges)
            }
            _ => {}
        }
    }

    for values in out.aggregates.values_mut() {
        values.sort_unstable();
        values.dedup();
    }
    for values in out.contains.values_mut() {
        values.sort_unstable();
        values.dedup();
    }
    for values in out.references.values_mut() {
        values.sort_unstable();
        values.dedup();
    }
    for values in out.defines_type.values_mut() {
        values.sort_unstable_by_key(|(relationship_id, _)| *relationship_id);
        values.dedup();
    }
    out.material_associations
        .sort_unstable_by_key(|association| association.relationship_id);
    out.classification_associations
        .sort_unstable_by_key(|association| association.relationship_id);
    out.document_associations
        .sort_unstable_by_key(|association| association.relationship_id);
    out.group_memberships.sort_unstable_by_key(|membership| {
        (
            membership.relationship_id,
            membership.group_id,
            membership.object_id,
        )
    });
    out.product_assignments.sort_unstable_by_key(|assignment| {
        (
            assignment.relationship_id,
            assignment.product_id,
            assignment.object_id,
        )
    });
    out.voids
        .sort_unstable_by_key(|relationship| relationship.relationship_id);
    out.fills
        .sort_unstable_by_key(|relationship| relationship.relationship_id);
    out.edges
        .edges
        .sort_unstable_by_key(|item| (item.relationship_id, item.relating_id, item.related_id));
    out
}

fn add_single_to_many(
    record: &EntityRecord,
    type_upper: &str,
    relating_index: usize,
    related_index: usize,
    adjacency: &mut BTreeMap<u32, Vec<u32>>,
    edges: &mut RelationshipData,
) {
    let Some(relating) = reference(record.attributes.get(relating_index)) else {
        return;
    };
    for related in refs(record.attributes.get(related_index)) {
        adjacency.entry(relating).or_default().push(related);
        edges
            .edges
            .push(edge(record, type_upper, relating, related));
    }
}

fn add_many_to_single(
    record: &EntityRecord,
    type_upper: &str,
    related_index: usize,
    relating_index: usize,
    adjacency: &mut BTreeMap<u32, Vec<u32>>,
    edges: &mut RelationshipData,
) {
    let Some(relating) = reference(record.attributes.get(relating_index)) else {
        return;
    };
    for related in refs(record.attributes.get(related_index)) {
        adjacency.entry(relating).or_default().push(related);
        edges
            .edges
            .push(edge(record, type_upper, relating, related));
    }
}

fn add_many_to_many(
    record: &EntityRecord,
    type_upper: &str,
    related_index: usize,
    relating_index: usize,
    edges: &mut RelationshipData,
) {
    for relating in refs(record.attributes.get(relating_index)) {
        for related in refs(record.attributes.get(related_index)) {
            edges
                .edges
                .push(edge(record, type_upper, relating, related));
        }
    }
}

fn add_single_to_single(
    record: &EntityRecord,
    type_upper: &str,
    relating_index: usize,
    related_index: usize,
    edges: &mut RelationshipData,
) {
    if let (Some(relating), Some(related)) = (
        reference(record.attributes.get(relating_index)),
        reference(record.attributes.get(related_index)),
    ) {
        edges
            .edges
            .push(edge(record, type_upper, relating, related));
    }
}

fn edge(
    record: &EntityRecord,
    type_upper: &str,
    relating_id: u32,
    related_id: u32,
) -> RelationshipEdge {
    RelationshipEdge {
        relationship_id: record.id,
        relationship_type: canonical_relationship_type(type_upper).to_string(),
        relating_id,
        related_id,
    }
}

fn canonical_relationship_type(type_upper: &str) -> &str {
    match type_upper {
        "IFCRELAGGREGATES" => "IfcRelAggregates",
        "IFCRELNESTS" => "IfcRelNests",
        "IFCRELCONTAINEDINSPATIALSTRUCTURE" => "IfcRelContainedInSpatialStructure",
        "IFCRELREFERENCEDINSPATIALSTRUCTURE" => "IfcRelReferencedInSpatialStructure",
        "IFCRELDEFINESBYTYPE" => "IfcRelDefinesByType",
        "IFCRELDEFINESBYPROPERTIES" => "IfcRelDefinesByProperties",
        "IFCRELSERVICESBUILDINGS" => "IfcRelServicesBuildings",
        "IFCRELASSOCIATESMATERIAL" => "IfcRelAssociatesMaterial",
        "IFCRELASSOCIATESCLASSIFICATION" => "IfcRelAssociatesClassification",
        "IFCRELASSOCIATESDOCUMENT" => "IfcRelAssociatesDocument",
        "IFCRELVOIDSELEMENT" => "IfcRelVoidsElement",
        "IFCRELFILLSELEMENT" => "IfcRelFillsElement",
        "IFCRELCONNECTSELEMENTS" => "IfcRelConnectsElements",
        "IFCRELCONNECTSPATHELEMENTS" => "IfcRelConnectsPathElements",
        "IFCRELCONNECTSPORTTOELEMENT" => "IfcRelConnectsPortToElement",
        "IFCRELCONNECTSPORTS" => "IfcRelConnectsPorts",
        "IFCRELSPACEBOUNDARY" => "IfcRelSpaceBoundary",
        "IFCRELSPACEBOUNDARY1STLEVEL" => "IfcRelSpaceBoundary1stLevel",
        "IFCRELSPACEBOUNDARY2NDLEVEL" => "IfcRelSpaceBoundary2ndLevel",
        "IFCRELASSIGNSTOGROUP" => "IfcRelAssignsToGroup",
        "IFCRELASSIGNSTOGROUPBYFACTOR" => "IfcRelAssignsToGroupByFactor",
        "IFCRELASSIGNSTOPRODUCT" => "IfcRelAssignsToProduct",
        _ => "IfcRelationship",
    }
}
