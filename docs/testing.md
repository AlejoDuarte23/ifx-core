# Testing strategy

`ifx-core` supports IFC2X3, IFC4, and the registered IFC4X3 releases.

The suite uses three complementary levels of verification.

For new-schema work, use the [strict local compatibility command](ifc-validation.md).
It adds original IFC2X3/IFC4/IFC4X3 fixtures and a hash-checked local model corpus.
It fails on missing inputs, stale builds, geometry differences, and incomplete
extraction. It does not run CI.

## Self-contained IfcOpenShell parity matrix

`tests/test_feature_matrix.py` creates small valid IFC files with IfcOpenShell,
serializes them to STEP, parses those bytes with `ifx-core`, and independently
derives the expected results from the IfcOpenShell model.

The spatial matrix runs against IFC4 and IFC4X3 in metres and millimetres. It
checks:

- exact edges for aggregation, nesting, containment, spatial references, type
  assignment, material association, voiding, and opening filling;
- the complete attached hierarchy and orphan detection;
- node identity, names, long names, direct elements, references, and children;
- site, building/facility, storey, space, and spatial-zone indexes;
- direct and placement-derived storey elevations in metres;
- reverse container and storey maps, including aggregate/nest descendants; and
- all currently recognized IFC4X3 facility and facility-part hierarchy types.

The relationship matrix additionally checks property definitions,
classifications, documents, groups and group factors, product assignments,
element/path connections, ports, and all three space-boundary levels.

`tests/test_system_services.py` checks source system-to-building edges, multiple
systems/buildings, JSON export, and unchanged spatial containment in IFC2X3,
IFC4, and IFC4X3 ADD2. The source-schema tests check that exporter `.NULL.` bar
surfaces are omitted while quoted `NULL` text and valid bar-surface values are
retained.

The opening matrix checks exact `IfcRelVoidsElement` and `IfcRelFillsElement`
edges, dedicated forward/reverse indexes, and spatial ancestry propagated from
the host element through each opening to its filling element.

The project-unit matrix checks IFC4 and IFC4X3 SI, conversion-based, derived,
and monetary units, including symbols, SI scales, and derived exponents.

Dedicated matrices cover nested classification paths and type inheritance,
document-reference merging and type inheritance, group/zone/system membership,
assignment factors, port topology, path priorities, space-boundary metadata,
projected CRS/map conversions, and `IfcSite` latitude/longitude fallback.

The material matrix runs against IFC4 and IFC4X3. It checks:

- plain materials, layer sets, profile sets, constituent sets, and lists;
- layer-set and profile-set usage indirection;
- material names, descriptions, categories, thicknesses, ventilation flags,
  priorities, profiles, fractions, and ordered leaves;
- direct assignments, type inheritance, direct precedence, multiple
  associations, duplicate-definition removal, and deterministic ordering; and
- native Python and JSON API equivalence after applying JSON's required
  stringification of numeric object keys.

These tests do not require a checked-in IFC fixture and therefore run in CI.

## Rust invariants and error behavior

CI runs `cargo test --workspace --locked` across all four internal crates and
the root crate. Original product and mapped-source fixtures cover streaming
row equivalence and shared mesh registration without external model files.

`tests/core.rs` covers behavior for which IfcOpenShell is not the correct
oracle: cycle termination, deterministic output, dangling references, missing
projects/entities, schema rejection, multiple-association ordering, and the
IFClite-compatible spatial propagation contract.

## Optional large-model regression

`tests/test_ifcopenshell_parity.py` compares every supported relationship and
typed semantic output against a real IFC model through IfcOpenShell. It is
skipped when the model is unavailable. Set
`IFX_PARITY_MODEL` to run it with a local model:

```bash
IFX_PARITY_MODEL=/absolute/path/model.ifc .venv/bin/python -m pytest -m integration -q
```

The self-contained matrix is the branch-coverage suite. Large models add scale
and real-world exporter variation, so additional known models can be exercised
through the same environment variable without becoming repository assets.

## Remote VIKTOR corpus

Five IFC4 models from
[`viktor-platform/ifc-sample-models`](https://github.com/viktor-platform/ifc-sample-models)
are tested through pinned raw GitHub URLs. The IFC files are downloaded only for
the test run and are never committed to this repository. The upstream commit
and file hashes are recorded in `tests/viktor_corpus.json`.

```bash
IFX_RUN_REMOTE_CORPUS=1 .venv/bin/python -m pytest -m corpus -q
```

The corpus runs weekly and can also be started manually through GitHub Actions.

## Local commands

```bash
cargo fmt -p ifx-core --check
cargo clippy -p ifx-core --all-targets --all-features --no-deps -- -D warnings
cargo test --workspace --locked
env -u CONDA_PREFIX uv run maturin develop --uv
.venv/bin/python -m pytest -q
```

On systems without Conda, omit `env -u CONDA_PREFIX`.
