# Source schema registry

The STEP decoder keeps the declared source schema separate from the geometry
routing enum. This prevents older attributes from receiving newer names. For
example, IFC2X3 `IfcSpace.InteriorOrExteriorSpace` is not `PredefinedType`.
The source class stays `IfcProxy` even when the geometry router uses the modern
proxy implementation.

| Path | Purpose |
| --- | --- |
| `crates/step/schema/sources.json` | Official buildingSMART source URLs and SHA-256 hashes |
| `scripts/generate-source-schemas.py` | Original EXPRESS-to-Rust table generator |
| `crates/step/src/schema/generated/` | Sorted entity names, parents and inherited attribute slots |
| `crates/step/src/schema/header.rs` | Bounded header reader that ignores quoted text and comments |
| `crates/step/src/schema/mod.rs` | Exact release lookup, attribute registry and inheritance checks |
| `tests/test_source_schemas.py` | Full attribute-table comparison with IfcOpenShell and old metadata checks |

The registry covers IFC2X3 TC1, IFC4 ADD2 TC1, IFC4X3 RC4, and IFC4X3 ADD2.
Unknown labels fail. Family labels select the listed registry. The decoder reads
source context once for each file; geometry jobs receive that context without
reading the header again. Position-based geometry reads remain unchanged where
the source layouts agree. Grid placement uses named attributes and the owning
grid frame for IFC2X3 and IFC4.

Use `DecodedEntity.attribute_names()`, `source_name()` and `get_named()` for
source semantics. Use `ifc_type` for geometry dispatch. Root semantic records
provide the same named access through `EntityRecord.get()`.

`model_data` and complete/streaming extraction retain source `IfcTypeObject`
definitions in `object_types.definitions`, keyed by STEP ID. Each definition has
its source class, GlobalId, name, description, and scalar attributes.
`object_types.types_by_element` holds the linked type IDs from
`IfcRelDefinesByType`. Shared definitions are exported once, duplicate links
are removed, and unresolved type IDs do not create invented definitions.
Inherited property sets keep their existing occurrence-precedence rules.
`tests/test_object_types.py` compares the source fields with IfcOpenShell in
IFC2X3, IFC4, and IFC4X3 ADD2, including shared and missing type links.

The shared entity decoder treats the exporter marker `.NULL.` in `BarSurface`
as an unset value, like `$`. Quoted text such as `'NULL'`, valid enums including
`IfcNullStyle.NULL`, and unknown logical values keep their values. The relationship
graph includes `IfcRelServicesBuildings`
edges from each source system to each served building. These edges do not change
spatial containment. Focused tests cover both cases in IFC2X3, IFC4, and IFC4X3
ADD2 as part of [the IFC2X3 support work](https://github.com/AlejoDuarte23/spectral/issues/320).

Run `python3 scripts/generate-source-schemas.py` to regenerate the tables.
Missing EXPRESS inputs download from the recorded official URLs and must match
the recorded hashes. They stay in the ignored `target/schema-sources/` folder.
Run with `--check` to check the generated files. The normal Rust build uses the
checked-in generated tables and needs no schema download.

The validation matrix has 30 independently generated fixtures. Native checks
compare world bounds, area and closed volume. The WASM matrix checks streaming
and mesh validity. A frontend WASM regression checks IFC2X3 streaming against the
complete extraction. See `docs/ifc-validation.md` for the local reference checks.

The shared geometry kernel still has unsupported representation types. The
independent property reader supports all seven property forms, material/profile
sets, and the older typed material/profile subtypes. It uses source field names.
Nested reads stop at 16 levels, 4,096 properties per set, and 4,096 values per
list/table column. Read issues remain visible in values and the coverage report.
A successful load or finite mesh does not prove complete geometry equivalence.
Private corpus models and detailed reports stay outside Git.
