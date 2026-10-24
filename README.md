# IFX core

One Rust IFC engine for native Python and browser WebAssembly. It reads IFC2X3, IFC4 and IFC4X3 models. Geometry, properties, quantities, placements, units, materials, spatial data, and relationships come from this core.

```python
import ifx_core

model = ifx_core.extract_ifc(open("building.ifc", "rb").read(), "high")
mesh = model["geometry"]["elements"][42]
properties = model["entities"]["entities"][42]["property_sets"]
spatial = model["model"]["spatial"]
```

`extract_ifc` uses the same Rust extraction function as WASM. It tessellates once. Python receives `f64` vertex and `u32` face buffers for NumPy. Separate `model_data`, `model_data_json`, `entity_data`, `geometry_data_buffers`, and `geometry_data_json` methods are available when only one part is needed.

Geometry and placements use absolute IFC world coordinates in metres, with Z up. The recorded RTC offset is already included. Do not add it again. Properties and quantities keep their source units. Use the reported unit scale for each dimension.

## Layout

| Path | Purpose |
| --- | --- |
| `src/` | IFX semantic extraction, unified entry point, Python and WASM bindings |
| `crates/step/` | Local STEP parser and source-schema tables |
| `crates/geometry/` | Local geometry and CSG kernel |
| `crates/processing/` | Local mesh pipeline |
| `crates/entities/` | Local properties, quantities, attributes, and placements |
| `pkg/` | Generated browser WASM module |
| `tests/` | Core, geometry, and IfcOpenShell parity checks |

No external IFClite package is used. IFX includes an adapted source port. See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md), [UPSTREAM_SOURCE.json](UPSTREAM_SOURCE.json), and [LICENSE](LICENSE). Keep the MPL terms, attribution, and matching source when you distribute a native or WASM build.

The property reader keeps single, enumerated, list, bounded, table, reference, and complex values. Optional `details`, `unit_id`, and `issue` fields preserve structure, source units, and read limits. Material and profile property sets are under `model.materials`. The `model.coverage` report counts source classes, metadata rows, mesh elements, unknown records, and read issues. These counts do not prove complete geometry accuracy.

## Build and check

Python 3.10 or later and the pinned Rust toolchain are required.

```sh
uv sync --group dev --no-install-project
uv run --no-sync maturin develop --uv --release
.venv/bin/python -m pytest -m 'not corpus and not integration'
cargo test --workspace --locked
cargo clippy -p ifx-core --all-targets --all-features --no-deps -- -D warnings
./scripts/build-wasm.sh
```

The WASM build exports `extractIfcJson(bytes, quality)` and `modelDataJson(bytes)`. The IFX TypeScript loader calls it in a Web Worker. The JSON boundary is the first implementation; large models can use more memory than the native buffer path.

Use `maturin build --release --out dist` for a native wheel, and `maturin sdist --out dist` for its matching source archive. The source archive includes the local crates and provenance file.
