import json
import subprocess
import sys
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import pytest

import ifx_core
from scripts.ifc_validation import runner
from scripts.ifc_validation.checks import (
    Findings,
    check_entities,
    check_geometry,
    geometry_products,
    reference_geometry,
)
from scripts.ifc_validation.fixtures import FEATURES, SCHEMAS, make_fixture
from scripts.ifc_validation.manifest import declared_schema, file_hash, inventory, load_manifest
from scripts.ifc_validation.mesh import Tolerances, compare_metrics, mesh_metrics

BoxFixture = tuple[bytes, ifcopenshell.file, dict[str, object]]


@pytest.mark.parametrize("schema", SCHEMAS)
@pytest.mark.parametrize("feature", FEATURES)
def test_original_fixtures_have_independent_geometry_expectations(
    schema: str, feature: str
) -> None:
    source, expected = make_fixture(schema, feature)
    assert make_fixture(schema, feature)[0] == source
    model = ifcopenshell.file.from_string(source.decode())
    assert model.schema_identifier == schema
    if feature == "grid-placement":
        declaration = ifcopenshell.ifcopenshell_wrapper.schema_by_name(schema).declaration_by_name(
            "IfcGridPlacement"
        )
        names = [attribute.name() for attribute in declaration.all_attributes()]
        assert names == (
            ["PlacementRelTo", "PlacementLocation", "PlacementRefDirection"]
            if schema == "IFC4X3_ADD2"
            else ["PlacementLocation", "PlacementRefDirection"]
        )
        assert model.by_id(
            expected["element_id"]
        ).ObjectPlacement.PlacementLocation.OffsetDistances == (0.0, 0.0, 3.0)
        return
    products, _ = geometry_products(model)
    reference = reference_geometry(model, products)
    assert set(reference) == {product.id() for product in products}
    assert compare_metrics(expected, reference[expected["element_id"]], Tolerances()) == []


@pytest.fixture
def original_box() -> tuple[bytes, object, dict[str, object]]:
    source, expected = make_fixture("IFC4", "metres")
    return source, ifcopenshell.file.from_string(source.decode()), expected


def test_geometry_comparison_accepts_different_triangulations(original_box: BoxFixture) -> None:
    _, model, expected = original_box
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    shape = ifcopenshell.geom.create_shape(settings, model.by_id(expected["element_id"]))
    vertices = np.array(shape.geometry.verts).reshape(-1, 3)
    faces = np.array(shape.geometry.faces).reshape(-1, 3)
    reference = mesh_metrics(vertices, faces)
    centroid = vertices[faces[0]].mean(axis=0)
    a, b, c = faces[0]
    index = len(vertices)
    subdivided = np.vstack((faces[1:], [[a, b, index], [b, c, index], [c, a, index]]))
    candidate = mesh_metrics(np.vstack((vertices, centroid)), subdivided)
    assert candidate["triangles"] != reference["triangles"]
    assert compare_metrics(reference, candidate, Tolerances()) == []


def test_geometry_comparison_rejects_wrong_units_and_open_solids(original_box: BoxFixture) -> None:
    _, model, _ = original_box
    products, _ = geometry_products(model)
    reference = next(iter(reference_geometry(model, products).values()))
    shifted = {**reference, "lower": [1000.0, 2000.0, 3000.0], "volume_m3": 24000.0}
    assert "lower bounds differ" in compare_metrics(reference, shifted, Tolerances())
    assert "solid volume differs" in compare_metrics(reference, shifted, Tolerances())
    opened = {**reference, "closed": False, "volume_m3": None}
    assert compare_metrics(reference, opened, Tolerances())


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1.0])
def test_invalid_tolerances_fail(invalid: float) -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        Tolerances(bounds_m=invalid)


def test_invalid_vertices_and_indices_fail() -> None:
    with pytest.raises(ValueError, match="nonfinite"):
        mesh_metrics(np.array([[0.0, 0.0, float("nan")]]), np.array([[0, 0, 0]]))
    with pytest.raises(ValueError, match="outside"):
        mesh_metrics(np.array([[0.0, 0.0, 0.0]]), np.array([[0, 0, 1]]))


def test_missing_geometry_cannot_pass(original_box: BoxFixture) -> None:
    _, model, _ = original_box
    products, _ = geometry_products(model)
    reference = reference_geometry(model, products)
    result = check_geometry(
        model,
        {"up_axis": "Z", "units": "m", "elements": {}, "element_count": 0},
        reference,
        Tolerances(),
    )
    assert result["status"] == "fail"
    assert result["failure_counts"]["candidate_geometry_missing"] == 1


def test_missing_attributes_and_wrong_class_cannot_pass(original_box: BoxFixture) -> None:
    source, model, expected = original_box
    data = ifx_core.entity_data(source)
    data["entities"][expected["element_id"]]["ifc_type"] = "IfcColumn"
    data["entities"][expected["element_id"]]["property_sets"] = []
    result = check_entities(model, data)
    assert result["status"] == "fail"
    assert result["failure_counts"]["identity.ifc_type"] == 1
    assert result["failure_counts"]["property_sets"] == 1


def test_header_inventory_handles_quotes_comments_and_cr_lines(tmp_path: Path) -> None:
    path = tmp_path / "quoted-header.ifc"
    path.write_bytes(
        b"ISO-10303-21;\rHEADER;\r/* FILE_SCHEMA(('IFC4')); ENDSEC; */\r"
        b"FILE_DESCRIPTION(('FILE_SCHEMA((''IFC4X3'')); ENDSEC;'),'2;1');\r"
        b"FILE_SCHEMA ( ( 'IFC2X3' ) );\rENDSEC;\rDATA;\rENDSEC;"
    )
    assert declared_schema(path) == "IFC2X3"


@pytest.mark.parametrize(
    "record",
    ["", "FILE_SCHEMA(('IFC4','IFC2X3'));", "FILE_SCHEMA(('IFC4'));FILE_SCHEMA(('IFC2X3'));"],
)
def test_ambiguous_or_missing_header_fails(tmp_path: Path, record: str) -> None:
    path = tmp_path / "invalid-header.ifc"
    path.write_text(f"ISO-10303-21;HEADER;{record}ENDSEC;DATA;ENDSEC;")
    with pytest.raises(ValueError):
        declared_schema(path)


def test_inventory_deduplicates_and_manifest_detects_changes(tmp_path: Path) -> None:
    source, _ = make_fixture("IFC2X3", "metres")
    (tmp_path / "first.ifc").write_bytes(source)
    (tmp_path / "duplicate.IFC").write_bytes(source)
    manifest = inventory(tmp_path, "IFC2X3")
    assert len(manifest["models"]) == 1
    assert manifest["duplicates"] == 1
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    assert len(load_manifest(path)) == 1
    Path(manifest["models"][0]["path"]).write_bytes(source + b"\n")
    with pytest.raises(ValueError, match="SHA-256 differs"):
        load_manifest(path)


def test_manifest_cannot_silently_skip_a_missing_model(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "models": [
                    {
                        "id": "required-model",
                        "schema": "IFC2X3",
                        "sha256": "a" * 64,
                        "path": "missing.ifc",
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="required model is missing"):
        load_manifest(path)


def test_missing_or_stale_build_stamp_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp = tmp_path / "build.json"
    monkeypatch.setattr(runner, "STAMP", stamp)
    with pytest.raises(RuntimeError, match="build stamp is missing"):
        runner.preflight()
    stamp.write_text(json.dumps({"source_sha256": "old", "binary": {}}))
    with pytest.raises(RuntimeError, match="native build is stale"):
        runner.preflight()


def test_missing_reference_dependency_is_not_a_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original_import = builtins.__import__

    def import_without_reference(name: str, *args: object, **kwargs: object) -> object:
        if name == "ifcopenshell":
            raise ModuleNotFoundError("IfcOpenShell is not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_reference)
    with pytest.raises(ModuleNotFoundError, match="IfcOpenShell is not installed"):
        runner.preflight()


def test_empty_manifest_command_writes_failure_report(tmp_path: Path) -> None:
    manifest = tmp_path / "empty-manifest.json"
    manifest.write_text(json.dumps({"version": 1, "models": []}))
    report = tmp_path / "failure-report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ifc_validation",
            "check",
            "--manifest",
            str(manifest),
            "--report",
            str(report),
        ],
        cwd=runner.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(report.read_text())["status"] == "fail"


def test_full_native_validation_passes_a_supported_model(
    tmp_path: Path,
    original_box: BoxFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _, _ = original_box
    model = tmp_path / "supported-model.ifc"
    model.write_bytes(source)
    monkeypatch.setattr(
        runner, "preflight", lambda: {"validation_sha256": runner.validation_hash()}
    )
    report = tmp_path / "native-report.json"
    result = runner.run_suite(
        [
            {
                "id": "supported-model",
                "schema": "IFC4",
                "path": str(model),
                "sha256": file_hash(model),
            }
        ],
        report,
        timeout=30,
        limits=Tolerances(),
        include_fixtures=False,
    )
    assert result["status"] == "pass"
    assert result["browser_verified"] is False
    assert result["expected_case_count"] == 1
    assert result["cases"][0]["stages"]["extraction"]["status"] == "pass"


def test_worker_timeout_is_a_failure(tmp_path: Path, original_box: BoxFixture) -> None:
    source, _, _ = original_box
    path = tmp_path / "required-model.ifc"
    path.write_bytes(source)
    result = runner.run_case(
        {
            "id": "required-model",
            "path": str(path),
            "schema": "IFC4",
            "sha256": file_hash(path),
            "tolerances": {"bounds_m": 0.002, "area_relative": 0.02, "volume_relative": 0.02},
        },
        tmp_path,
        timeout=0.001,
    )
    assert result["status"] == "fail"
    assert result["error"] == "timeout"
    assert result["native_extraction_verified"] is False


def test_partial_geometry_does_not_count_as_a_full_load(tmp_path: Path) -> None:
    source, analytic = make_fixture("IFC4", "metres")
    model = ifcopenshell.file.from_string(source.decode())
    model.remove(model.by_type("IfcProject")[0])
    source = model.to_string().encode()
    path = tmp_path / "projectless-box.ifc"
    path.write_bytes(source)
    result = runner.run_case(
        {
            "id": "projectless-box",
            "path": str(path),
            "schema": "IFC4",
            "sha256": file_hash(path),
            "analytic": analytic,
            "tolerances": {"bounds_m": 0.002, "area_relative": 0.02, "volume_relative": 0.02},
        },
        tmp_path,
        timeout=30,
    )
    assert result["stages"]["geometry"]["status"] == "pass"
    assert result["stages"]["model"]["status"] == "fail"
    assert result["status"] == "fail"
    assert result["native_extraction_verified"] is False


def test_ifc4x3_manifest_round_trip(tmp_path: Path) -> None:
    source, _ = make_fixture("IFC4X3_ADD2", "metres")
    (tmp_path / "infrastructure.ifc").write_bytes(source)
    manifest = tmp_path / "infrastructure-models.json"
    manifest.write_text(json.dumps(inventory(tmp_path, "IFC4X3_ADD2")))
    assert len(load_manifest(manifest)) == 1


def test_unset_scalar_property_can_be_omitted(original_box: BoxFixture) -> None:
    source, _, _ = original_box
    model = ifcopenshell.file.from_string(source.decode())
    pset = model.by_type("IfcPropertySet")[0]
    unset = model.create_entity("IfcPropertySingleValue", Name="Unset", NominalValue=None)
    pset.HasProperties = (*pset.HasProperties, unset)
    data = ifx_core.entity_data(model.to_string().encode())
    assert check_entities(model, data)["status"] == "pass"


def test_diagnostic_examples_include_different_failure_categories() -> None:
    issues = Findings()
    for element_id in range(500):
        issues.add("uncompared_complex_property", element_id, "ListProperty")
    issues.add("attribute_value", 501, "InteriorOrExteriorSpace")
    result = issues.result()
    assert result["failure_counts"]["uncompared_complex_property"] == 500
    assert any(item["check"] == "attribute_value" for item in result["examples"])
    assert len(result["examples"]) <= 200


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4", "IFC4X3_ADD2"])
def test_all_property_forms_have_an_independent_reference(schema: str) -> None:
    from property_fixtures import make_property_fixture

    source, ids = make_property_fixture(schema)
    model = ifcopenshell.file.from_string(source.decode())
    actual = ifx_core.entity_data(source)
    assert check_entities(model, actual)["status"] == "pass"
    properties = actual["entities"][ids["wall"]]["property_sets"][0]["properties"]
    bounded = next(prop for prop in properties if prop["name"] == "Range")
    bounded["details"]["lower"]["value"] = "999"
    assert check_entities(model, actual)["status"] == "fail"


@pytest.mark.parametrize("name,field", [("Lengths", "values"), ("Curve", "defined")])
def test_wrong_non_scalar_property_values_cannot_pass(name: str, field: str) -> None:
    from property_fixtures import make_property_fixture

    source, ids = make_property_fixture("IFC2X3")
    model = ifcopenshell.file.from_string(source.decode())
    actual = ifx_core.entity_data(source)
    properties = actual["entities"][ids["wall"]]["property_sets"][0]["properties"]
    prop = next(prop for prop in properties if prop["name"] == name)
    prop["details"][field][0]["value"] = "999"
    assert check_entities(model, actual)["status"] == "fail"
