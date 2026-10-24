import json

import ifcopenshell
import pytest

import ifx_core
from scripts.ifc_validation.checks import check_model
from scripts.ifc_validation.fixtures import SCHEMAS, make_fixture


@pytest.mark.parametrize("schema", SCHEMAS)
def test_system_service_edges_match_source_and_preserve_spatial_containment(
    schema: str,
) -> None:
    source, _ = make_fixture(schema, "metres")
    model = ifcopenshell.file.from_string(source.decode())
    project = model.by_type("IfcProject")[0]
    wall = model.by_type("IfcWall")[0]
    buildings = [
        model.create_entity(
            "IfcBuilding",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=project.OwnerHistory,
            Name=f"Building {index}",
        )
        for index in range(2)
    ]
    systems = [
        model.create_entity(
            "IfcSystem",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=project.OwnerHistory,
            Name=name,
        )
        for name in ["Ventilation", "Heating"]
    ]
    for system, served_buildings in [
        (systems[0], list(reversed(buildings))),
        (systems[1], [buildings[0]]),
        (systems[0], [buildings[1]]),
    ]:
        model.create_entity(
            "IfcRelServicesBuildings",
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=project.OwnerHistory,
            RelatingSystem=system,
            RelatedBuildings=served_buildings,
        )
    model.create_entity(
        "IfcRelAggregates",
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=project.OwnerHistory,
        RelatingObject=project,
        RelatedObjects=buildings,
    )
    model.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=project.OwnerHistory,
        RelatingStructure=buildings[0],
        RelatedElements=[wall],
    )
    source = model.to_string().encode()
    data = ifx_core.model_data(source)
    expected = {
        (relation.id(), relation.RelatingSystem.id(), building.id())
        for relation in model.by_type("IfcRelServicesBuildings")
        for building in relation.RelatedBuildings
    }
    actual = {
        (edge["relationship_id"], edge["relating_id"], edge["related_id"])
        for edge in data["relationships"]["edges"]
        if edge["relationship_type"] == "IfcRelServicesBuildings"
    }
    assert actual == expected
    assert len(actual) == 4
    assert data["spatial"]["element_to_container"][wall.id()] == buildings[0].id()
    assert all(system.id() not in data["spatial"]["element_to_container"] for system in systems)
    assert check_model(model, data)["status"] == "pass"
    assert json.loads(ifx_core.model_data_json(source))["relationships"] == data["relationships"]
