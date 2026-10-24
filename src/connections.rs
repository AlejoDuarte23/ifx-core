use std::collections::BTreeMap;

use crate::{
    model::{
        ConnectionsData, ElementConnection, PortConnection, PortDefinition,
        PortToElementConnection, SpaceBoundary,
    },
    parser::{enumeration, integers, reference, string, ParsedModel},
};

pub(crate) fn build_connections(model: &ParsedModel) -> ConnectionsData {
    let ports = model
        .entity_types
        .iter()
        .filter_map(|(id, type_name)| {
            if type_name != "IFCDISTRIBUTIONPORT" {
                return None;
            }
            let record = model.records.get(id)?;
            Some((
                *id,
                PortDefinition {
                    express_id: *id,
                    ifc_type: "IfcDistributionPort".to_string(),
                    global_id: string(record.attributes.first()),
                    name: string(record.attributes.get(2)),
                    description: string(record.attributes.get(3)),
                    object_type: string(record.attributes.get(4)),
                    flow_direction: enumeration(record.attributes.get(7)),
                    predefined_type: enumeration(record.attributes.get(8)),
                    system_type: enumeration(record.attributes.get(9)),
                },
            ))
        })
        .collect();

    let mut element_connections = Vec::new();
    let mut port_to_element = Vec::new();
    let mut port_connections = Vec::new();
    let mut space_boundaries = Vec::new();
    for record in model.records.values() {
        let type_name = model
            .entity_types
            .get(&record.id)
            .map(String::as_str)
            .unwrap_or_default();
        match type_name {
            "IFCRELCONNECTSELEMENTS" | "IFCRELCONNECTSPATHELEMENTS" => {
                let (Some(relating_element_id), Some(related_element_id)) = (
                    reference(record.attributes.get(5)),
                    reference(record.attributes.get(6)),
                ) else {
                    continue;
                };
                let is_path = type_name == "IFCRELCONNECTSPATHELEMENTS";
                element_connections.push(ElementConnection {
                    relationship_id: record.id,
                    relationship_type: if is_path {
                        "IfcRelConnectsPathElements".to_string()
                    } else {
                        "IfcRelConnectsElements".to_string()
                    },
                    relating_element_id,
                    related_element_id,
                    connection_geometry_id: reference(record.attributes.get(4)),
                    relating_priorities: if is_path {
                        integers(record.attributes.get(7))
                    } else {
                        Vec::new()
                    },
                    related_priorities: if is_path {
                        integers(record.attributes.get(8))
                    } else {
                        Vec::new()
                    },
                    related_connection_type: is_path
                        .then(|| enumeration(record.attributes.get(9)))
                        .flatten(),
                    relating_connection_type: is_path
                        .then(|| enumeration(record.attributes.get(10)))
                        .flatten(),
                });
            }
            "IFCRELCONNECTSPORTTOELEMENT" => {
                if let (Some(port_id), Some(element_id)) = (
                    reference(record.attributes.get(4)),
                    reference(record.attributes.get(5)),
                ) {
                    port_to_element.push(PortToElementConnection {
                        relationship_id: record.id,
                        port_id,
                        element_id,
                    });
                }
            }
            "IFCRELCONNECTSPORTS" => {
                if let (Some(relating_port_id), Some(related_port_id)) = (
                    reference(record.attributes.get(4)),
                    reference(record.attributes.get(5)),
                ) {
                    port_connections.push(PortConnection {
                        relationship_id: record.id,
                        relating_port_id,
                        related_port_id,
                        realizing_element_id: reference(record.attributes.get(6)),
                    });
                }
            }
            "IFCRELSPACEBOUNDARY"
            | "IFCRELSPACEBOUNDARY1STLEVEL"
            | "IFCRELSPACEBOUNDARY2NDLEVEL" => {
                if let (Some(space_id), Some(element_id)) = (
                    reference(record.attributes.get(4)),
                    reference(record.attributes.get(5)),
                ) {
                    space_boundaries.push(SpaceBoundary {
                        relationship_id: record.id,
                        relationship_type: canonical_boundary_type(type_name).to_string(),
                        space_id,
                        element_id,
                        connection_geometry_id: reference(record.attributes.get(6)),
                        physical_or_virtual: enumeration(record.attributes.get(7)),
                        internal_or_external: enumeration(record.attributes.get(8)),
                        parent_boundary_id: reference(record.attributes.get(9)),
                        corresponding_boundary_id: reference(record.attributes.get(10)),
                    });
                }
            }
            _ => {}
        }
    }
    element_connections.sort_unstable_by_key(|item| item.relationship_id);
    port_to_element.sort_unstable_by_key(|item| item.relationship_id);
    port_connections.sort_unstable_by_key(|item| item.relationship_id);
    space_boundaries.sort_unstable_by_key(|item| item.relationship_id);

    let mut connections_by_element = BTreeMap::new();
    for connection in &element_connections {
        push_unique(
            &mut connections_by_element,
            connection.relating_element_id,
            connection.relationship_id,
        );
        push_unique(
            &mut connections_by_element,
            connection.related_element_id,
            connection.relationship_id,
        );
    }
    let mut ports_by_element = BTreeMap::new();
    let mut elements_by_port = BTreeMap::new();
    for connection in &port_to_element {
        push_unique(
            &mut ports_by_element,
            connection.element_id,
            connection.port_id,
        );
        push_unique(
            &mut elements_by_port,
            connection.port_id,
            connection.element_id,
        );
    }
    let mut connected_ports = BTreeMap::new();
    for connection in &port_connections {
        push_unique(
            &mut connected_ports,
            connection.relating_port_id,
            connection.related_port_id,
        );
        push_unique(
            &mut connected_ports,
            connection.related_port_id,
            connection.relating_port_id,
        );
    }
    let mut boundaries_by_space = BTreeMap::new();
    let mut boundaries_by_element = BTreeMap::new();
    for boundary in &space_boundaries {
        push_unique(
            &mut boundaries_by_space,
            boundary.space_id,
            boundary.relationship_id,
        );
        push_unique(
            &mut boundaries_by_element,
            boundary.element_id,
            boundary.relationship_id,
        );
    }

    ConnectionsData {
        element_connections,
        connections_by_element,
        ports,
        port_to_element,
        ports_by_element,
        elements_by_port,
        port_connections,
        connected_ports,
        space_boundaries,
        boundaries_by_space,
        boundaries_by_element,
    }
}

fn push_unique(map: &mut BTreeMap<u32, Vec<u32>>, key: u32, value: u32) {
    let values = map.entry(key).or_default();
    if !values.contains(&value) {
        values.push(value);
        values.sort_unstable();
    }
}

fn canonical_boundary_type(type_name: &str) -> &str {
    match type_name {
        "IFCRELSPACEBOUNDARY1STLEVEL" => "IfcRelSpaceBoundary1stLevel",
        "IFCRELSPACEBOUNDARY2NDLEVEL" => "IfcRelSpaceBoundary2ndLevel",
        _ => "IfcRelSpaceBoundary",
    }
}
