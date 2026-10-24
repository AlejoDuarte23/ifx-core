import re
import subprocess
import sys
from pathlib import Path

import ifcopenshell
import pytest

import ifx_core
from scripts.ifc_validation.fixtures import make_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_generated_schemas_are_current() -> None:
    subprocess.run(
        [sys.executable, "scripts/generate-source-schemas.py", "--check"], cwd=ROOT, check=True
    )


@pytest.mark.parametrize(
    ("name", "schema"), [("ifc2x3", "IFC2X3"), ("ifc4", "IFC4"), ("ifc4x3_add2", "IFC4X3_ADD2")]
)
def test_all_source_attributes_match_reference_registry(name: str, schema: str) -> None:
    registry = ifcopenshell.ifcopenshell_wrapper.schema_by_name(schema)
    source = (ROOT / f"crates/step/src/schema/generated/{name}.rs").read_text()
    definitions = re.findall(r'name: "(\w+)".*?attributes: &\[(.*?)\]', source)
    assert len(definitions) > 600
    for entity, attributes in definitions:
        expected = [
            attribute.name() for attribute in registry.declaration_by_name(entity).all_attributes()
        ]
        assert re.findall(r'"(.*?)"', attributes) == expected, entity


def test_old_attributes_keep_their_names_and_source_classes() -> None:
    source, _ = make_fixture("IFC2X3", "metres")
    model = ifcopenshell.file.from_string(source.decode())
    model.create_entity(
        "IfcSpace",
        GlobalId=ifcopenshell.guid.new(),
        Name="Room",
        InteriorOrExteriorSpace="INTERNAL",
    )
    model.create_entity(
        "IfcProxy", GlobalId=ifcopenshell.guid.new(), Name="Equipment", ProxyType="PRODUCT"
    )
    rows = ifx_core.entity_data(model.to_string().encode(), attributes=True)["entities"]
    room = next(row for row in rows.values() if row["name"] == "Room")
    attrs = {a["name"]: a["value"] for a in room["attributes"]}
    assert attrs["InteriorOrExteriorSpace"] == "INTERNAL"
    assert "PredefinedType" not in attrs
    assert (
        next(row for row in rows.values() if row["name"] == "Equipment")["ifc_type"] == "IfcProxy"
    )


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4", "IFC4X3_ADD2"])
@pytest.mark.parametrize("marker", ["$", ".NULL."])
def test_unset_bar_surface_is_omitted_and_literal_null_text_is_preserved(
    schema: str, marker: str
) -> None:
    source, _ = make_fixture(schema, "metres")
    model = ifcopenshell.file.from_string(source.decode())
    bar = model.create_entity(
        "IfcReinforcingBar",
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=model.by_type("IfcProject")[0].OwnerHistory,
        Name="NULL",
        Tag="NULL",
        NominalDiameter=16.0,
        BarSurface="PLAIN",
    )
    valid_bar = model.create_entity(
        "IfcReinforcingBar",
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=bar.OwnerHistory,
        Name="Textured bar",
        BarSurface="TEXTURED",
    )
    source = model.to_string().replace(".PLAIN.", marker).encode()
    reference = ifcopenshell.file.from_string(source.decode())
    assert reference.by_id(bar.id()).BarSurface is None

    rows = ifx_core.entity_data(source, attributes=True)["entities"]
    attributes = {item["name"]: item["value"] for item in rows[bar.id()]["attributes"]}
    assert "BarSurface" not in attributes
    assert rows[bar.id()]["name"] == "NULL"
    assert attributes["Tag"] == "NULL"
    assert attributes["NominalDiameter"] == "16"
    assert (
        next(
            item["value"]
            for item in rows[valid_bar.id()]["attributes"]
            if item["name"] == "BarSurface"
        )
        == "TEXTURED"
    )


def test_old_document_fields_and_calendar_dates() -> None:
    source, _ = make_fixture("IFC2X3", "metres")
    model = ifcopenshell.file.from_string(source.decode())
    date = model.create_entity(
        "IfcCalendarDate", DayComponent=23, MonthComponent=10, YearComponent=2026
    )
    document = model.create_entity(
        "IfcDocumentInformation",
        DocumentId="SPEC-01",
        Name="Specification",
        Purpose="Design",
        IntendedUse="Construction",
        Scope="Building",
        Revision="B",
        ValidFrom=date,
    )
    data = ifx_core.model_data(model.to_string().encode())
    exported = data["documents"]["definitions"][document.id()]
    assert exported["identification"] == "SPEC-01"
    assert exported["purpose"] == "Design"
    assert exported["intended_use"] == "Construction"
    assert exported["scope"] == "Building"
    assert exported["revision"] == "B"
    assert exported["valid_from"] == "2026-10-23"


def test_old_meshes_and_rows_keep_the_same_source_class() -> None:
    source, _ = make_fixture("IFC2X3", "metres")
    model = ifcopenshell.file.from_string(source.decode())
    wall = model.by_type("IfcWall")[0]
    proxy = model.create_entity(
        "IfcProxy",
        GlobalId=ifcopenshell.guid.new(),
        Name="Equipment",
        ProxyType="PRODUCT",
        Representation=wall.Representation,
        ObjectPlacement=wall.ObjectPlacement,
    )
    data = ifx_core.extract_ifc(model.to_string().encode(), "medium")
    assert data["geometry"]["elements"][proxy.id()]["ifc_type"] == "IfcProxy"
    assert data["entities"]["entities"][proxy.id()]["ifc_type"] == "IfcProxy"
