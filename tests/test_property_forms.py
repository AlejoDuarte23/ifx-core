import ifcopenshell
import pytest
from property_fixtures import make_property_fixture

import ifx_core


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4", "IFC4X3_ADD2"])
def test_all_property_forms_keep_values_and_source_structure(schema: str) -> None:
    source, ids = make_property_fixture(schema)
    exported = ifx_core.entity_data(source)["entities"][ids["wall"]]["property_sets"][0][
        "properties"
    ]
    props = {value["name"]: value for value in exported}
    assert props["Wrapped identifier"]["value"] == "line break"
    assert props["Shape"]["value"] == "ROUND"
    assert props["Shape"]["details"]["kind"] == "enumerated"
    assert [v["value"] for v in props["Lengths"]["details"]["values"]] == ["200", "450"]
    assert props["Lengths"]["unit_id"] == ids["unit"]
    bounds = props["Range"]["details"]
    assert bounds["lower"]["value"] == "100"
    assert bounds["upper"]["value"] == "500"
    assert (
        bounds["set_point"] is None if schema == "IFC2X3" else bounds["set_point"]["value"] == "300"
    )
    assert [v["value"] for v in props["Curve"]["details"]["defined"]] == ["10", "40"]
    assert props["Curve"]["details"]["expression"] == "y=x*x*10"
    assert props["Material reference"]["details"]["express_id"] == ids["material"]
    assert props["Material reference"]["value"] == "Validation material"
    children = props["Dimensions"]["details"]["properties"]
    assert [(p["name"], p["value"]) for p in children] == [("Height", "4"), ("Lengths", "200, 450")]
    assert all("issue" not in prop for prop in exported)


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4", "IFC4X3_ADD2"])
def test_material_and_profile_properties_use_source_layout(schema: str) -> None:
    source, ids = make_property_fixture(schema)
    data = ifx_core.model_data(source)["materials"]
    assert data["properties_by_material"][ids["material"]] == [ids["material_set"]]
    assert data["properties_by_profile"][ids["profile"]] == [ids["profile_set"]]
    material = data["property_sets"][ids["material_set"]]
    assert material["name"] == "Material stiffness"
    assert material["resource_kind"] == "material"
    assert material["properties"][0]["value"] == "210000"
    assert material["properties"][1]["details"]["values"][0]["value"] == "ROUND"
    profile = data["property_sets"][ids["profile_set"]]
    assert profile["name"] == "Cross section"
    assert (
        next(prop for prop in profile["properties"] if prop["name"] == "CrossSectionArea")["value"]
        == "6"
    )


def test_nested_property_cycles_are_reported() -> None:
    source, ids = make_property_fixture("IFC2X3")
    model = ifcopenshell.file.from_string(source.decode())
    parent = model.by_id(ids["complex"])
    parent.HasProperties = [parent]
    data = ifx_core.entity_data(model.to_string().encode())
    complex_value = next(
        p
        for p in data["entities"][ids["wall"]]["property_sets"][0]["properties"]
        if p["name"] == "Dimensions"
    )
    assert complex_value["details"]["properties"][0]["issue"] == "cycle"


def test_missing_property_references_are_reported() -> None:
    source, ids = make_property_fixture("IFC4")
    model = ifcopenshell.file.from_string(source.decode())
    reference = next(p for p in model.by_type("IfcPropertyReferenceValue"))
    source = (
        model.to_string().replace(f"#{reference.PropertyReference.id()});", "#999999999);").encode()
    )
    props = ifx_core.entity_data(source)["entities"][ids["wall"]]["property_sets"][0]["properties"]
    value = next(p for p in props if p["name"] == "Material reference")
    assert value["issue"] == "missing_reference"
    assert value["details"]["express_id"] == 999999999


def test_property_depth_and_value_limits_are_visible() -> None:
    source, ids = make_property_fixture("IFC4")
    model = ifcopenshell.file.from_string(source.decode())
    child = model.create_entity(
        "IfcPropertySingleValue", Name="Leaf", NominalValue=model.create_entity("IfcLabel", "end")
    )
    for index in range(20):
        child = model.create_entity(
            "IfcComplexProperty", Name=f"Level {index}", UsageName="Nested", HasProperties=[child]
        )
    values = model.create_entity(
        "IfcPropertyListValue",
        Name="Many values",
        ListValues=[model.create_entity("IfcInteger", index) for index in range(4100)],
    )
    model.by_id(ids["pset"]).HasProperties = [child, values]
    props = ifx_core.entity_data(model.to_string().encode())["entities"][ids["wall"]][
        "property_sets"
    ][0]["properties"]
    current = props[0]
    for _ in range(16):
        current = current["details"]["properties"][0]
    assert current["issue"] == "depth_limit"
    assert props[1]["issue"] == "value_limit"
    assert len(props[1]["details"]["values"]) == 4096


def test_ifc2x3_typed_material_properties_are_retained() -> None:
    source, ids = make_property_fixture("IFC2X3")
    model = ifcopenshell.file.from_string(source.decode())
    prop = model.create_entity(
        "IfcMechanicalMaterialProperties",
        Material=model.by_id(ids["material"]),
        YoungModulus=210000.0,
        PoissonRatio=0.3,
    )
    data = ifx_core.model_data(model.to_string().encode())["materials"]
    result = data["property_sets"][prop.id()]
    assert result["resource_id"] == ids["material"]
    assert {value["name"]: value["value"] for value in result["properties"]} == {
        "YoungModulus": "210000",
        "PoissonRatio": "0.3",
    }
