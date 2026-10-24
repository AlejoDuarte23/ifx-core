import ifcopenshell
from property_fixtures import make_property_fixture

import ifx_core


def test_analysis_reports_scan_without_claiming_geometry_checks() -> None:
    source, _ = make_property_fixture("IFC2X3")
    report = ifx_core.model_data(source)["coverage"]
    assert report["scan_complete"] is True
    assert report["total_records"] == report["distinct_entity_ids"]
    assert report["unknown_records"] == 0
    assert report["classes"]["IFCWALL"]["is_product"] is True
    assert report["extraction"] is None


def test_complete_extraction_reports_product_and_mesh_coverage() -> None:
    source, _ = make_property_fixture("IFC2X3")
    report = ifx_core.extract_ifc(source, "medium")["model"]["coverage"]
    assert report["classes"]["IFCWALL"]["exported_rows"] == 1
    assert report["classes"]["IFCWALL"]["mesh_elements"] == 1
    extraction = report["extraction"]
    assert extraction["source_products"] == 1
    assert extraction["mesh_elements"] == 1
    assert extraction["unmeshed_represented_products"]["count"] == 0
    assert extraction["products_without_metadata"]["count"] == 0
    assert extraction["meshes_without_metadata"]["count"] == 0


def test_unknown_types_and_duplicate_ids_are_visible() -> None:
    source, _ = make_property_fixture("IFC4")
    source = source.replace(
        b"ENDSEC;\nEND-ISO",
        b"#8000=IFCVENDORRECORD('one');\n#8000=IFCVENDORRECORD('two');\nENDSEC;\nEND-ISO",
    )
    report = ifx_core.model_data(source)["coverage"]
    assert report["unknown_records"] == 2
    assert report["classes"]["IFCVENDORRECORD"]["scanned"] == 2
    assert report["classes"]["IFCVENDORRECORD"]["declared"] is False
    assert report["duplicate_entity_ids"] == [8000]
    assert report["total_records"] == report["distinct_entity_ids"] + 1


def test_non_mesh_representation_is_reported_and_not_hidden() -> None:
    source, ids = make_property_fixture("IFC4")
    model = ifcopenshell.file.from_string(source.decode())
    shape = model.by_type("IfcShapeRepresentation")[0]
    shape.Items = [
        model.create_entity(
            "IfcGeometricSet",
            Elements=[model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0])],
        )
    ]
    shape.RepresentationType = "GeometricSet"
    result = ifx_core.extract_ifc(model.to_string().encode(), "medium")
    report = result["model"]["coverage"]["extraction"]
    assert report["represented_products"] == 1
    assert report["unmeshed_represented_products"]["count"] == 1
    assert report["unmeshed_represented_products"]["sample_ids"] == [ids["wall"]]
    assert report["mesh_elements"] == 0
