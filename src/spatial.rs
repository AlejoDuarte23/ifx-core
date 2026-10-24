use std::collections::BTreeSet;

use ifx_step::AttributeValue;

use crate::{
    model::{SpatialData, SpatialNode},
    parser::{is_spatial_type, number, reference, string, EntityRecord, ParsedModel},
    relationships::Relations,
};

struct SpatialBuilder<'a> {
    model: &'a ParsedModel,
    relations: &'a Relations,
    data: SpatialData,
    visited: BTreeSet<u32>,
}

pub(crate) fn build_spatial(model: &ParsedModel, relations: &Relations) -> SpatialData {
    let mut builder = SpatialBuilder {
        model,
        relations,
        data: SpatialData {
            project_id: model.project_ids.first().copied(),
            referenced_by_structure: relations.references.clone(),
            ..SpatialData::default()
        },
        visited: BTreeSet::new(),
    };

    if let Some(project_id) = model.project_ids.first() {
        let root = builder.build_node(*project_id);
        builder.data.roots.push(root);
    }

    let attached: BTreeSet<u32> = builder.visited.clone();
    builder.data.orphan_spatial_ids = model
        .entity_types
        .iter()
        .filter_map(|(id, type_name)| {
            (is_spatial_type(type_name) && !attached.contains(id)).then_some(*id)
        })
        .collect();
    builder.data
}

impl SpatialBuilder<'_> {
    fn build_node(&mut self, express_id: u32) -> SpatialNode {
        let record = self.model.records.get(&express_id);
        let type_upper = self
            .model
            .entity_types
            .get(&express_id)
            .map(String::as_str)
            .unwrap_or("IFCUNKNOWN");
        let ifc_type = record
            .map(|record| record.ifc_type.clone())
            .unwrap_or_else(|| type_upper.to_string());
        let raw_name = record.and_then(|record| string(record.attributes.get(2)));
        let raw_long_name = record.and_then(|record| {
            let index = if type_upper == "IFCPROJECT" { 5 } else { 7 };
            string(record.attributes.get(index))
        });
        let name = raw_name
            .clone()
            .or_else(|| raw_long_name.clone())
            .unwrap_or_else(|| format!("Entity #{}", express_id));
        let long_name = raw_long_name.filter(|value| value != &name);
        let global_id = record.and_then(|record| string(record.attributes.first()));
        let elevation = if type_upper == "IFCBUILDINGSTOREY" {
            record.and_then(|record| self.storey_elevation(record))
        } else {
            None
        };

        if !self.visited.insert(express_id) {
            return SpatialNode {
                express_id,
                ifc_type,
                global_id,
                name,
                long_name,
                elevation,
                children: Vec::new(),
                elements: Vec::new(),
                referenced_elements: self
                    .relations
                    .references
                    .get(&express_id)
                    .cloned()
                    .unwrap_or_default(),
            };
        }

        if let Some(value) = elevation {
            self.data.storey_elevations.insert(express_id, value);
        }

        let raw_contained = self
            .relations
            .contains
            .get(&express_id)
            .cloned()
            .unwrap_or_default();
        let mut elements = Vec::new();
        let mut contained_spatial = Vec::new();
        for id in raw_contained {
            let target_type = self
                .model
                .entity_types
                .get(&id)
                .map(String::as_str)
                .unwrap_or_default();
            if is_spatial_type(target_type) && target_type != "IFCPROJECT" {
                contained_spatial.push(id);
            } else {
                elements.push(id);
            }
        }
        elements.sort_unstable();
        elements.dedup();

        let mut child_ids = BTreeSet::new();
        for child_id in self
            .relations
            .aggregates
            .get(&express_id)
            .into_iter()
            .flatten()
            .chain(contained_spatial.iter())
        {
            let target_type = self
                .model
                .entity_types
                .get(child_id)
                .map(String::as_str)
                .unwrap_or_default();
            if is_spatial_type(target_type) && target_type != "IFCPROJECT" {
                child_ids.insert(*child_id);
            }
        }
        let children: Vec<SpatialNode> = child_ids
            .iter()
            .map(|child_id| self.build_node(*child_id))
            .collect();

        match type_upper {
            "IFCBUILDINGSTOREY" => {
                self.data.by_storey.insert(express_id, elements.clone());
                for element_id in &elements {
                    self.assign_storey_with_descendants(*element_id, express_id);
                }
                for child_id in &child_ids {
                    self.data
                        .element_to_storey
                        .entry(*child_id)
                        .or_insert(express_id);
                }
            }
            "IFCBUILDING" | "IFCFACILITY" | "IFCBRIDGE" | "IFCROAD" | "IFCRAILWAY"
            | "IFCMARINEFACILITY" => {
                self.data.by_building.insert(express_id, elements.clone());
            }
            "IFCSITE" => {
                self.data.by_site.insert(express_id, elements.clone());
            }
            "IFCSPACE" | "IFCSPATIALZONE" => {
                self.data.by_space.insert(express_id, elements.clone());
            }
            _ => {}
        }

        if type_upper != "IFCPROJECT" {
            for element_id in &elements {
                self.assign_container_with_descendants(*element_id, express_id);
            }
        }

        SpatialNode {
            express_id,
            ifc_type,
            global_id,
            name,
            long_name,
            elevation,
            children,
            elements,
            referenced_elements: self
                .relations
                .references
                .get(&express_id)
                .cloned()
                .unwrap_or_default(),
        }
    }

    fn assign_storey_with_descendants(&mut self, root: u32, storey_id: u32) {
        self.data.element_to_storey.insert(root, storey_id);
        let mut stack = vec![root];
        let mut seen = BTreeSet::from([root]);
        while let Some(current) = stack.pop() {
            for child in self.semantic_children(current) {
                if seen.insert(child) {
                    self.data
                        .element_to_storey
                        .entry(child)
                        .or_insert(storey_id);
                    stack.push(child);
                }
            }
        }
    }

    fn assign_container_with_descendants(&mut self, root: u32, container_id: u32) {
        self.data.element_to_container.insert(root, container_id);
        let mut stack = vec![root];
        let mut seen = BTreeSet::from([root]);
        while let Some(current) = stack.pop() {
            for child in self.semantic_children(current) {
                if seen.insert(child) {
                    self.data
                        .element_to_container
                        .entry(child)
                        .or_insert(container_id);
                    stack.push(child);
                }
            }
        }
    }

    fn semantic_children(&self, parent: u32) -> Vec<u32> {
        let mut children = self
            .relations
            .aggregates
            .get(&parent)
            .cloned()
            .unwrap_or_default();
        children.extend(self.relations.voids.iter().filter_map(|relationship| {
            (relationship.element_id == parent).then_some(relationship.opening_id)
        }));
        children.extend(self.relations.fills.iter().filter_map(|relationship| {
            (relationship.opening_id == parent).then_some(relationship.filling_id)
        }));
        children.sort_unstable();
        children.dedup();
        children
    }

    fn storey_elevation(&self, record: &EntityRecord) -> Option<f64> {
        number(record.attributes.get(9))
            .or_else(|| self.placement_elevation(record))
            .map(|value| value * self.model.length_unit_scale)
    }

    fn placement_elevation(&self, record: &EntityRecord) -> Option<f64> {
        let placement_id = reference(record.attributes.get(5))?;
        let placement = self.model.records.get(&placement_id)?;
        let axis_id = reference(placement.attributes.get(1))?;
        let axis = self.model.records.get(&axis_id)?;
        let location_id = reference(axis.attributes.first())?;
        let location = self.model.records.get(&location_id)?;
        match location.attributes.first()? {
            AttributeValue::List(coords) => number(coords.get(2)),
            _ => None,
        }
    }
}
