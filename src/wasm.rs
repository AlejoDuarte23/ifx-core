// SPDX-License-Identifier: MPL-2.0
use wasm_bindgen::prelude::*;

#[wasm_bindgen(js_name = extractIfcStreamingJson)]
pub fn extract_ifc_streaming_json(
    bytes: &[u8],
    quality: &str,
    on_batch: &js_sys::Function,
) -> Result<String, JsValue> {
    use ifx_entities::{build_export_model_with_options, ModelOptions};
    use ifx_processing::{
        build_geometry_data_export, process_geometry_streaming_world, StreamingOptions,
        TessellationQuality,
    };
    crate::parser::supported_schema(bytes)
        .map_err(|error| JsValue::from_str(&error.to_string()))?;
    let quality = TessellationQuality::parse_label(quality)
        .ok_or_else(|| JsValue::from_str("Unknown geometry quality"))?;
    let mut callback_error = None;
    let result = process_geometry_streaming_world(
        bytes,
        StreamingOptions {
            initial_batch_size: 8,
            throughput_batch_size: 64,
            fast_first_batch: true,
            tessellation_quality: quality,
            ..StreamingOptions::default()
        },
        |meshes, processed, total, offset, rotation| {
            if callback_error.is_some() {
                return;
            }
            let geometry = build_geometry_data_export(meshes, offset, rotation);
            let event =
                serde_json::json!({ "geometry": geometry, "processed": processed, "total": total });
            match serde_json::to_string(&event) {
                Ok(json) => {
                    if let Err(error) = on_batch.call1(&JsValue::NULL, &JsValue::from_str(&json)) {
                        callback_error = Some(error);
                    }
                }
                Err(_) => callback_error = Some(JsValue::from_str("Cannot encode geometry batch")),
            }
        },
    );
    if let Some(error) = callback_error {
        return Err(error);
    }
    let rotation = if result.mesh_coordinate_space.as_deref() == Some("site_local") {
        result.site_transform.as_deref()
    } else {
        None
    };
    let geometry = build_geometry_data_export(
        &result.meshes,
        result.metadata.coordinate_info.origin_shift,
        rotation,
    );
    let mut model =
        crate::analyze_ifc(bytes).map_err(|error| JsValue::from_str(&error.to_string()))?;
    let options = ModelOptions::default()
        .with_placements(true)
        .with_inherit_type_properties(true)
        .with_attributes(true);
    let entities = build_export_model_with_options(bytes, &options);
    crate::coverage::complete(&mut model, &entities, &geometry, bytes);
    serde_json::to_string(&crate::extraction::Extraction {
        geometry,
        entities,
        model,
    })
    .map_err(|error| JsValue::from_str(&error.to_string()))
}

/// Call in a Web Worker for large files. The browser and Python use the same kernel.
#[wasm_bindgen(js_name = extractIfcJson)]
pub fn extract_ifc_json(bytes: &[u8], quality: &str) -> Result<String, JsValue> {
    let data =
        crate::extract(bytes, quality).map_err(|error| JsValue::from_str(&error.to_string()))?;
    serde_json::to_string(&data).map_err(|error| JsValue::from_str(&error.to_string()))
}

#[wasm_bindgen(js_name = modelDataJson)]
pub fn model_data_json(bytes: &[u8]) -> Result<String, JsValue> {
    let data = crate::analyze_ifc(bytes).map_err(|error| JsValue::from_str(&error.to_string()))?;
    serde_json::to_string(&data).map_err(|error| JsValue::from_str(&error.to_string()))
}
