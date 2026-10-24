use crate::{parser::ParsedModel, ModelData};
use ifx_entities::{ExportModel, PropValue, PropertyDetails};
use ifx_processing::GeometryDataExport;
use ifx_step::EntityScanner;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

const SAMPLE_LIMIT: usize = 100;

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct CoverageReport {
    pub scan_complete: bool,
    pub total_records: usize,
    pub distinct_entity_ids: usize,
    pub duplicate_entity_ids: Vec<u32>,
    pub unknown_records: usize,
    pub classes: BTreeMap<String, ClassCoverage>,
    pub extraction: Option<ExtractionCoverage>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ClassCoverage {
    pub declared: bool,
    pub is_root: bool,
    pub is_product: bool,
    pub scanned: usize,
    pub decoded_for_model_data: usize,
    pub exported_rows: usize,
    pub mesh_elements: usize,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct IdExamples {
    pub count: usize,
    pub sample_ids: Vec<u32>,
    pub truncated: bool,
}

impl IdExamples {
    fn add(&mut self, id: u32) {
        self.count += 1;
        if self.sample_ids.len() < SAMPLE_LIMIT {
            self.sample_ids.push(id);
        } else {
            self.truncated = true;
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ExtractionCoverage {
    pub source_products: usize,
    pub exported_rows: usize,
    pub mesh_elements: usize,
    pub represented_products: usize,
    pub products_without_metadata: IdExamples,
    pub unmeshed_represented_products: IdExamples,
    pub meshes_without_metadata: IdExamples,
    pub property_issue_occurrences: BTreeMap<String, usize>,
}

pub(crate) fn scan(model: &ParsedModel) -> CoverageReport {
    let mut result = CoverageReport {
        scan_complete: true,
        distinct_entity_ids: model.entity_types.len(),
        duplicate_entity_ids: model.duplicate_ids.iter().copied().collect(),
        ..CoverageReport::default()
    };
    for (name, count) in &model.source_counts {
        let declared = model.source_schema.entity(name).is_some();
        result.total_records += count;
        if !declared {
            result.unknown_records += count;
        }
        result.classes.insert(
            name.clone(),
            ClassCoverage {
                declared,
                scanned: *count,
                is_root: model.source_schema.is_subtype(name, "IFCROOT"),
                is_product: model.source_schema.is_subtype(name, "IFCPRODUCT"),
                ..ClassCoverage::default()
            },
        );
    }
    for record in model.records.values() {
        if let Some(class) = result
            .classes
            .get_mut(&record.ifc_type.to_ascii_uppercase())
        {
            class.decoded_for_model_data += 1;
        }
    }
    result
}

fn issues(properties: &[PropValue], counts: &mut BTreeMap<String, usize>) {
    for property in properties {
        if let Some(issue) = &property.issue {
            *counts.entry(issue.clone()).or_default() += 1;
        }
        if let Some(PropertyDetails::Complex { properties, .. }) = &property.details {
            issues(properties, counts);
        }
    }
}

pub(crate) fn complete(
    model: &mut ModelData,
    entities: &ExportModel,
    geometry: &GeometryDataExport,
    bytes: &[u8],
) {
    let metadata_ids: BTreeSet<_> = entities.entities.iter().map(|e| e.express_id).collect();
    let mesh_ids: BTreeSet<_> = geometry
        .elements
        .iter()
        .filter_map(|(id, mesh)| {
            (!mesh.vertices.is_empty() && !mesh.faces.is_empty()).then_some(*id)
        })
        .collect();
    let mut result = ExtractionCoverage {
        exported_rows: metadata_ids.len(),
        mesh_elements: mesh_ids.len(),
        ..ExtractionCoverage::default()
    };
    let mut products = BTreeSet::new();
    let mut scanner = EntityScanner::new(bytes);
    while let Some((id, name, _, _)) = scanner.next_entity() {
        if model
            .coverage
            .classes
            .get(&name.to_ascii_uppercase())
            .is_some_and(|c| c.is_product)
        {
            products.insert(id);
        }
    }
    result.source_products = products.len();
    for id in &products {
        if !metadata_ids.contains(id) {
            result.products_without_metadata.add(*id);
        }
    }
    for row in &entities.entities {
        if let Some(class) = model
            .coverage
            .classes
            .get_mut(&row.ifc_type.to_ascii_uppercase())
        {
            class.exported_rows += 1;
        }
        if products.contains(&row.express_id) && row.has_geometry {
            result.represented_products += 1;
            if !mesh_ids.contains(&row.express_id) {
                result.unmeshed_represented_products.add(row.express_id);
            }
        }
        for set in &row.property_sets {
            issues(&set.properties, &mut result.property_issue_occurrences);
        }
    }
    for (id, mesh) in &geometry.elements {
        if !mesh_ids.contains(id) {
            continue;
        }
        if let Some(class) = model
            .coverage
            .classes
            .get_mut(&mesh.ifc_type.to_ascii_uppercase())
        {
            class.mesh_elements += 1;
        }
        if !metadata_ids.contains(id) {
            result.meshes_without_metadata.add(*id);
        }
    }
    for set in model.materials.property_sets.values() {
        issues(&set.properties, &mut result.property_issue_occurrences);
    }
    model.coverage.extraction = Some(result);
}
