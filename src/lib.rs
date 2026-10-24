// SPDX-License-Identifier: MPL-2.0
mod coverage;
mod extraction;
pub use coverage::{ClassCoverage, CoverageReport, ExtractionCoverage, IdExamples};
#[cfg(feature = "python")]
mod python_geometry;
#[cfg(feature = "wasm")]
mod wasm;
pub use extraction::{extract, Extraction};

mod classifications;
mod connections;
mod documents;
mod georeferencing;
mod groups;
mod materials;
mod model;
mod object_types;
mod openings;
mod parser;
mod relationships;
mod resource_properties;
mod spatial;
mod units;

pub use model::*;

use thiserror::Error;

#[cfg(feature = "python")]
use pyo3::{exceptions::PyRuntimeError, prelude::*, types::PyModule};
#[cfg(feature = "python")]
use pythonize::pythonize;

#[derive(Debug, Error)]
pub enum Error {
    #[error("invalid IFC: {0}")]
    InvalidIfc(String),
    #[error("failed to parse IFC entity #{express_id}: {message}")]
    ParseEntity { express_id: u32, message: String },
    #[error("failed to serialize IFC relationship data: {0}")]
    Serialize(#[from] serde_json::Error),
}

pub fn analyze_ifc(ifc_bytes: &[u8]) -> Result<ModelData, Error> {
    let parsed = parser::parse_model(ifc_bytes)?;
    let relations = relationships::extract_relations(&parsed);
    let object_types = object_types::extract(&parsed, &relations);
    let spatial = spatial::build_spatial(&parsed, &relations);
    let openings = openings::build_openings(&relations);
    let classifications = classifications::build_classifications(&parsed, &relations);
    let documents = documents::build_documents(&parsed, &relations);
    let groups = groups::build_groups(&parsed, &relations);
    let connections = connections::build_connections(&parsed);
    let georeferencing = georeferencing::build_georeferencing(&parsed);
    let materials = materials::build_materials(&parsed, &relations, ifc_bytes);
    let units = units::build_units(&parsed);
    let coverage = coverage::scan(&parsed);
    Ok(ModelData {
        coverage,
        schema: parsed.schema,
        entity_count: parsed.entity_types.len(),
        length_unit_scale: parsed.length_unit_scale,
        units,
        relationships: relations.edges,
        object_types,
        spatial,
        openings,
        classifications,
        documents,
        groups,
        connections,
        georeferencing,
        materials,
    })
}

#[cfg(feature = "python")]
#[pyfunction]
fn model_data(py: Python<'_>, ifc_bytes: Vec<u8>) -> PyResult<Py<PyAny>> {
    let data = py
        .detach(|| analyze_ifc(&ifc_bytes))
        .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
    pythonize(py, &data)
        .map(Bound::unbind)
        .map_err(|error| PyRuntimeError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyfunction]
fn model_data_json(py: Python<'_>, ifc_bytes: Vec<u8>) -> PyResult<String> {
    py.detach(|| {
        let data = analyze_ifc(&ifc_bytes).map_err(|error| error.to_string())?;
        serde_json::to_string(&data).map_err(|error| error.to_string())
    })
    .map_err(PyRuntimeError::new_err)
}

#[cfg(feature = "python")]
#[pymodule]
fn ifx_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(model_data, module)?)?;
    module.add_function(wrap_pyfunction!(model_data_json, module)?)?;
    python_geometry::register(module)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add(
        "__doc__",
        "IFX native IFC geometry, properties, and relationships.",
    )?;
    Ok(())
}
