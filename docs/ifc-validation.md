# Local IFC compatibility validation

Use this command before enabling a new IFC schema. It compares the current
native core with IfcOpenShell and independently specified geometry dimensions.
It does not start GitHub Actions, upload models, or download a model corpus.

## Run

Use the repository's Python environment with the `dev` dependencies installed.
The reference dependency is pinned in `pyproject.toml`.

```bash
.venv/bin/python -m scripts.ifc_validation build
.venv/bin/python -m scripts.ifc_validation inventory ~/Downloads \
  --schema IFC2X3 --output /tmp/ifc2x3-models.json
.venv/bin/python -m scripts.ifc_validation check \
  --manifest /tmp/ifc2x3-models.json \
  --report /tmp/ifc2x3-validation.json
```

`build` compiles the working tree and records the Rust-source and native-library
SHA-256 hashes under the ignored `target/` directory. `check` rejects a missing
or stale build stamp. The report records these hashes, the validation-script
hash, Python, platform, and IfcOpenShell version.

`inventory` reads the actual `FILE_SCHEMA` header record, handles quoted text,
comments, and CR/LF line endings, and removes files with duplicate content. The
manifest stores absolute paths, declared schemas, file sizes, and SHA-256 hashes.
`check` requires every manifest file and verifies its content before processing.
Relative model paths are resolved from the manifest directory.

Keep the manifest, models, and full reports outside Git. Reports contain local
paths, source IDs, and property values.

## Checks

The default run includes 30 original fixtures: ten cases each for IFC2X3, IFC4,
and IFC4X3 ADD2. They cover metres, millimetres, feet, nested rotation, large
coordinates, nonuniform mapping, opening subtraction, legacy door styles/type
properties, grid placement, and quoted header keywords.

Fixtures are generated locally. Their GUIDs and timestamps are deterministic.
Their known dimensions independently check the reference tessellator. The grid
case uses an analytical reference because the installed IfcOpenShell geometry
engine does not resolve this fixture's grid topology. IFC4X3 explicitly sets
`PlacementRelTo`; IFC2X3 and IFC4 obtain the grid frame from the referenced axes.
The slot differences follow the source schema. See the buildingSMART
[grid placement definition](https://github.com/buildingSMART/IFC4.x-development/blob/ifc4.3-main/docs/schemas/resource/IfcGeometricConstraintResource/Entities/IfcGridPlacement.md).

Each fixture and manifest model has separate results for:

- model extraction: schema family, entity count, length units, exact supported
  relationship edges, spatial containment, and material-assignment IDs;
- full extraction: the public combined native extraction function must complete;
- entity export: product coverage, original class and identity fields, scalar
  declared attributes, all seven property forms in direct/inherited property
  sets, explicit unit IDs, nested structures, and quantities;
- reference geometry: represented products must have reference meshes; and
- candidate geometry: missing/extra IDs, identity, finite vertices, valid indices,
  zero-area triangles, world-space bounds, surface area, and closed-solid volume.

Opening meshes are included because the core's default extraction exports them.
Products without representations and products without a 3D Body/Facetation
representation are listed as explicit geometry exclusions. Orphan type-product
metadata rows are allowed by the existing export contract. Relationship classes
outside the supported extraction contract are counted separately. Property
comparisons use IfcOpenShell source entities, including reference properties
that its convenience property-set helper can omit. Unread values, cycles,
read limits, wrong bounds, list/table members, units, or references fail.

`tests/test_property_forms.py` checks IFC2X3, IFC4, and IFC4X3 material/profile
property layouts and read limits. `tests/test_coverage.py` checks unknown records,
duplicate IDs, metadata counts, and undrawn representations.
`tests/test_surface_extrusion.py` uses independent bounds and an 8 m² area for a
2 m line swept 4 m, both with and without an axis rotation. IfcOpenShell 0.8.5
cannot tessellate this direct Surface3D item; no reference-engine pass is claimed.

Different triangle counts are allowed. The default tolerances are 2 mm for bounds
and 2% for surface area and volume. These values are recorded in the report and
can be set with `--bounds-m`, `--area-relative`, and `--volume-relative`. Volume
is compared only when the reference mesh is closed and consistently oriented;
reference open meshes are listed. If that reference is closed, an open candidate
fails. These measurements do not prove exact surface equivalence.
An unset property value can be omitted. A nonempty candidate value for that
unset property fails the comparison.

## Failure behavior

Exit code `0` means every native case passed the stated checks. Code `1` means
one or more cases failed. Code `2` means setup or input validation failed.
Missing dependencies, missing/changed files, empty manifests, stale builds,
worker crashes, and timeouts cannot produce a pass.

Each model runs in a separate process. The default time limit is 180 seconds
per case; use `--timeout` to change it. The parent retains completed stages when
a worker fails. The report and a separate directory hold case results, original
fixtures, worker logs, elapsed times, and peak resident memory. Failure counts
cover every comparison; diagnostic examples are limited to 200 per stage.
Each failure category has at most 20 examples, so a frequent failure does not
hide other categories. On a timeout, memory is the peak observed at the last
completed checkpoint.

An IFC2X3 model can emit geometry while model extraction rejects its schema.
That result remains a failed native load. The geometry and entity results are
diagnostic and cannot override the model/extraction failure.

## Browser and release checks

This command validates the native core. It does not prove WASM or browser
behavior. The report always states `browser_verified: false`.

Before enabling IFC2X3 in the viewer, use the same verified source to build WASM
and check first rendered geometry, stable IDs/origin, progress completion,
cancellation, replacement, search, selection, measurements, sections, camera
stability, and large-file memory. IFC4 and IFC4X3 must retain their current
behavior. A native report alone must not enable a new viewer schema.

## Test the validation command

```bash
.venv/bin/python -m pytest -q tests/test_ifc_validation.py
.venv/bin/ruff check scripts/ifc_validation tests/test_ifc_validation.py
```

These tests verify the independent fixture expectations, alternate
triangulations, missing geometry/properties, invalid meshes/tolerances, quoted
headers, duplicate/changed/missing files, stale builds, worker timeouts, and the
difference between a geometry probe and a complete IFC2X3 load. They require the
reference dependency; they do not silently skip it.
