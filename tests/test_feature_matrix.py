import json
from collections import defaultdict, deque
from typing import Any

import pytest

import ifx_core

try:
    import ifcopenshell
    from ifc_fixtures import (
        as_bytes,
        classification_model,
        connection_model,
        document_model,
        georeference_model,
        group_model,
        material_model,
        opening_model,
        site_georeference_model,
        spatial_model,
        unit_model,
    )
    from ifcopenshell.util.element import get_container, get_material, get_materials
    from ifcopenshell.util.placement import get_storey_elevation
    from ifcopenshell.util.unit import calculate_unit_scale
except ModuleNotFoundError:
    pytest.skip("IfcOpenShell is required for parity tests", allow_module_level=True)


RELATIONSHIP_ATTRIBUTES = {
    "IfcRelAggregates": ("RelatingObject", "RelatedObjects"),
    "IfcRelNests": ("RelatingObject", "RelatedObjects"),
    "IfcRelContainedInSpatialStructure": ("RelatingStructure", "RelatedElements"),
    "IfcRelReferencedInSpatialStructure": ("RelatingStructure", "RelatedElements"),
    "IfcRelDefinesByType": ("RelatingType", "RelatedObjects"),
    "IfcRelServicesBuildings": ("RelatingSystem", "RelatedBuildings"),
    "IfcRelAssociatesMaterial": ("RelatingMaterial", "RelatedObjects"),
    "IfcRelAssociatesClassification": ("RelatingClassification", "RelatedObjects"),
    "IfcRelAssociatesDocument": ("RelatingDocument", "RelatedObjects"),
    "IfcRelVoidsElement": ("RelatingBuildingElement", "RelatedOpeningElement"),
    "IfcRelFillsElement": ("RelatingOpeningElement", "RelatedBuildingElement"),
    "IfcRelAssignsToGroup": ("RelatingGroup", "RelatedObjects"),
    "IfcRelAssignsToGroupByFactor": ("RelatingGroup", "RelatedObjects"),
    "IfcRelAssignsToProduct": ("RelatingProduct", "RelatedObjects"),
    "IfcRelConnectsElements": ("RelatingElement", "RelatedElement"),
    "IfcRelConnectsPathElements": ("RelatingElement", "RelatedElement"),
    "IfcRelConnectsPortToElement": ("RelatingPort", "RelatedElement"),
    "IfcRelConnectsPorts": ("RelatingPort", "RelatedPort"),
    "IfcRelSpaceBoundary": ("RelatingSpace", "RelatedBuildingElement"),
    "IfcRelSpaceBoundary1stLevel": ("RelatingSpace", "RelatedBuildingElement"),
    "IfcRelSpaceBoundary2ndLevel": ("RelatingSpace", "RelatedBuildingElement"),
}

MATERIAL_DEFINITION_TYPES = {
    "IfcMaterial",
    "IfcMaterialLayerSet",
    "IfcMaterialLayerSetUsage",
    "IfcMaterialProfileSet",
    "IfcMaterialProfileSetUsage",
    "IfcMaterialConstituentSet",
    "IfcMaterialList",
}


def oracle_edges(model: Any) -> set[tuple[int, str, int, int]]:
    return {
        (relationship.id(), relation_type, getattr(relationship, relating_attr).id(), related.id())
        for relation_type, (relating_attr, related_attr) in RELATIONSHIP_ATTRIBUTES.items()
        for relationship in model.by_type(relation_type)
        if relationship.is_a() == relation_type
        for related in related_entities(getattr(relationship, related_attr))
    }


def actual_edges(data: dict[str, Any]) -> set[tuple[int, str, int, int]]:
    return {
        (
            edge["relationship_id"],
            edge["relationship_type"],
            edge["relating_id"],
            edge["related_id"],
        )
        for edge in data["relationships"]["edges"]
    }


def related_entities(value: Any) -> list[Any]:
    return list(value) if isinstance(value, tuple) else [value]


def flatten_spatial(nodes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    flattened: dict[int, dict[str, Any]] = {}
    pending = list(nodes)
    while pending:
        node = pending.pop()
        flattened[node["express_id"]] = node
        pending.extend(node["children"])
    return flattened


def json_compatible(value: Any) -> Any:
    """Apply JSON's string-key rule to the native Python representation."""

    if isinstance(value, dict):
        return {
            str(key) if isinstance(key, int) else key: json_compatible(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [json_compatible(item) for item in value]
    return value


def is_spatial(entity: Any) -> bool:
    return entity.is_a("IfcSpatialElement") or entity.is_a() == "IfcProject"


def spatial_oracle(model: Any, project_id: int) -> tuple[dict[int, set[int]], set[int]]:
    children: dict[int, set[int]] = defaultdict(set)
    for relationship in model.by_type("IfcRelAggregates"):
        for related in relationship.RelatedObjects:
            if is_spatial(related) and related.is_a() != "IfcProject":
                children[relationship.RelatingObject.id()].add(related.id())
    for relationship in model.by_type("IfcRelContainedInSpatialStructure"):
        for related in relationship.RelatedElements:
            if is_spatial(related) and related.is_a() != "IfcProject":
                children[relationship.RelatingStructure.id()].add(related.id())

    attached = {project_id}
    pending = deque([project_id])
    while pending:
        for child_id in children[pending.popleft()]:
            if child_id not in attached:
                attached.add(child_id)
                pending.append(child_id)
    return children, attached


def direct_elements(model: Any, structure: Any) -> list[int]:
    return sorted(
        element.id()
        for relationship in model.by_type("IfcRelContainedInSpatialStructure")
        if relationship.RelatingStructure == structure
        for element in relationship.RelatedElements
        if not is_spatial(element)
    )


def referenced_elements(model: Any, structure: Any) -> list[int]:
    return sorted(
        element.id()
        for relationship in model.by_type("IfcRelReferencedInSpatialStructure")
        if relationship.RelatingStructure == structure
        for element in relationship.RelatedElements
    )


def reference_oracle(model: Any) -> dict[int, list[int]]:
    result: dict[int, list[int]] = defaultdict(list)
    for relationship in model.by_type("IfcRelReferencedInSpatialStructure"):
        result[relationship.RelatingStructure.id()].extend(
            element.id() for element in relationship.RelatedElements
        )
    return {key: sorted(set(values)) for key, values in result.items()}


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_opening_feature_matrix_matches_ifcopenshell(schema: str) -> None:
    model, handles = opening_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    openings = data["openings"]

    assert actual_edges(data) == oracle_edges(model)
    assert openings["voids"] == [
        {
            "relationship_id": handles["door_void"].id(),
            "element_id": handles["wall"].id(),
            "opening_id": handles["door_opening"].id(),
        },
        {
            "relationship_id": handles["window_void"].id(),
            "element_id": handles["wall"].id(),
            "opening_id": handles["window_opening"].id(),
        },
    ]
    assert openings["fills"] == [
        {
            "relationship_id": handles["door_fill"].id(),
            "opening_id": handles["door_opening"].id(),
            "filling_id": handles["door"].id(),
        },
        {
            "relationship_id": handles["window_fill"].id(),
            "opening_id": handles["window_opening"].id(),
            "filling_id": handles["window"].id(),
        },
    ]
    assert openings["openings_by_element"] == {
        handles["wall"].id(): sorted([handles["door_opening"].id(), handles["window_opening"].id()])
    }
    assert openings["elements_by_opening"] == {
        handles["door_opening"].id(): [handles["wall"].id()],
        handles["window_opening"].id(): [handles["wall"].id()],
    }
    assert openings["fillings_by_opening"] == {
        handles["door_opening"].id(): [handles["door"].id()],
        handles["window_opening"].id(): [handles["window"].id()],
    }
    assert openings["openings_by_filling"] == {
        handles["door"].id(): [handles["door_opening"].id()],
        handles["window"].id(): [handles["window_opening"].id()],
    }

    for key in ("wall", "door_opening", "window_opening", "door", "window"):
        entity = handles[key]
        assert data["spatial"]["element_to_container"][entity.id()] == get_container(entity).id()
        assert data["spatial"]["element_to_storey"][entity.id()] == handles["storey"].id()


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_project_units_match_ifcopenshell(schema: str) -> None:
    model, handles = unit_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    units = data["units"]

    assert units["assignment_id"] == handles["assignment"].id()
    assert units["by_type"]["LENGTHUNIT"]["symbol"] == "mm"
    assert units["by_type"]["LENGTHUNIT"]["si_scale"] == pytest.approx(calculate_unit_scale(model))
    assert units["by_type"]["AREAUNIT"]["symbol"] == "mm²"
    assert units["by_type"]["AREAUNIT"]["si_scale"] == pytest.approx(1e-6)
    assert units["by_type"]["PLANEANGLEUNIT"]["symbol"] == "°"
    assert units["by_type"]["PLANEANGLEUNIT"]["si_scale"] == pytest.approx(
        calculate_unit_scale(model, "PLANEANGLEUNIT")
    )
    flow = units["by_type"]["VOLUMETRICFLOWRATEUNIT"]
    assert flow["symbol"] == "m³/s"
    assert flow["si_scale"] == pytest.approx(1.0)
    assert [element["exponent"] for element in flow["elements"]] == [1, -1]
    assert units["by_type"]["MONETARYUNIT"] == {
        "express_id": handles["money"].id(),
        "ifc_type": "IfcMonetaryUnit",
        "unit_type": "MONETARYUNIT",
        "name": "USD",
        "symbol": "$",
        "si_scale": 1.0,
        "conversion_offset": None,
        "elements": [],
    }


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_classification_feature_matrix_matches_ifcopenshell(schema: str) -> None:
    model, handles = classification_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    classifications = data["classifications"]

    assert actual_edges(data) == oracle_edges(model)
    assert classifications["systems"] == {
        handles["system"].id(): {
            "express_id": handles["system"].id(),
            "source": "NBS",
            "edition": "2025",
            "edition_date": "2025-01-01",
            "name": "Uniclass 2015",
            "description": "Test classification system",
            "location": "https://example.test/uniclass",
            "reference_tokens": ["Pr"],
        }
    }
    assert classifications["references"][handles["parent"].id()] == {
        "express_id": handles["parent"].id(),
        "location": "https://example.test/uniclass/Pr_20",
        "identification": "Pr_20",
        "name": "Structural and general products",
        "referenced_source_id": handles["system"].id(),
        "description": "Parent classification",
        "sort": "20",
        "system_id": handles["system"].id(),
        "system_name": "Uniclass 2015",
        "path": ["Pr_20"],
    }
    assert classifications["references"][handles["child"].id()]["path"] == [
        "Pr_20",
        "Pr_20_93",
    ]
    assert classifications["associations"] == [
        {
            "relationship_id": handles[name].id(),
            "classification_id": handles[classification].id(),
            "related_objects": [handles[target].id()],
        }
        for name, classification, target in (
            ("direct_relationship", "child", "wall"),
            ("inherited_relationship", "parent", "wall_type"),
            ("duplicate_relationship", "child", "wall_type"),
            ("system_relationship", "system", "system_wall"),
        )
    ]
    assert classifications["element_classifications"][handles["wall"].id()] == [
        {
            "classification_id": handles["child"].id(),
            "inherited_from_type": None,
        },
        {
            "classification_id": handles["parent"].id(),
            "inherited_from_type": handles["wall_type"].id(),
        },
    ]
    assert classifications["element_classifications"][handles["system_wall"].id()] == [
        {
            "classification_id": handles["system"].id(),
            "inherited_from_type": None,
        }
    ]


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_document_feature_matrix_matches_ifcopenshell(schema: str) -> None:
    model, handles = document_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    documents = data["documents"]

    assert actual_edges(data) == oracle_edges(model)
    info_id = handles["information"].id()
    reference_id = handles["reference"].id()
    assert documents["definitions"][info_id] == {
        "express_id": info_id,
        "document_type": "DocumentInformation",
        "referenced_document_id": None,
        "identification": "DOC-001",
        "name": "Installation manual",
        "description": "Canonical document description",
        "location": "https://example.test/manual.pdf",
        "purpose": "Installation",
        "intended_use": "Construction",
        "scope": "Project",
        "revision": "B",
        "electronic_format": "application/pdf",
        "valid_from": "2025-01-01",
        "valid_until": "2030-01-01",
        "confidentiality": "PUBLIC",
        "status": "FINAL",
    }
    assert documents["definitions"][reference_id] == {
        **documents["definitions"][info_id],
        "express_id": reference_id,
        "document_type": "DocumentReference",
        "referenced_document_id": info_id,
        "description": "Reference-specific description",
        "location": "manual.pdf",
    }
    assert documents["associations"] == [
        {
            "relationship_id": handles[name].id(),
            "document_id": handles[document].id(),
            "related_objects": [handles[target].id()],
        }
        for name, document, target in (
            ("direct_relationship", "reference", "wall"),
            ("inherited_relationship", "information", "wall_type"),
            ("duplicate_relationship", "reference", "wall_type"),
        )
    ]
    assert documents["element_documents"][handles["wall"].id()] == [
        {
            "definition_id": reference_id,
            "inherited_from_type": None,
            "document": documents["definitions"][reference_id],
        },
        {
            "definition_id": info_id,
            "inherited_from_type": handles["wall_type"].id(),
            "document": documents["definitions"][info_id],
        },
    ]


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_group_feature_matrix_matches_ifcopenshell(schema: str) -> None:
    model, handles = group_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    groups = data["groups"]

    assert actual_edges(data) == oracle_edges(model)
    assert groups["definitions"][handles["group"].id()] == {
        "express_id": handles["group"].id(),
        "ifc_type": "IfcGroup",
        "global_id": handles["group"].GlobalId,
        "name": "Inspection group",
        "description": None,
        "object_type": "Review set",
        "long_name": None,
        "predefined_type": None,
    }
    assert groups["definitions"][handles["zone"].id()]["long_name"] == "Fire compartment A"
    assert groups["definitions"][handles["distribution_system"].id()] == {
        "express_id": handles["distribution_system"].id(),
        "ifc_type": "IfcDistributionSystem",
        "global_id": handles["distribution_system"].GlobalId,
        "name": "Supply air",
        "description": None,
        "object_type": None,
        "long_name": "Supply air system",
        "predefined_type": "VENTILATION",
    }
    expected_memberships = [
        {
            "relationship_id": relationship.id(),
            "group_id": group.id(),
            "object_id": member.id(),
            "factor": factor,
        }
        for relationship, group, members, factor in (
            (
                handles["group_relationship"],
                handles["group"],
                [handles["wall"], handles["space"]],
                None,
            ),
            (handles["zone_relationship"], handles["zone"], [handles["space"]], None),
            (handles["factor_relationship"], handles["system"], [handles["wall"]], 0.25),
            (
                handles["distribution_relationship"],
                handles["distribution_system"],
                [handles["wall"]],
                None,
            ),
        )
        for member in members
    ]
    assert groups["memberships"] == expected_memberships
    assert groups["members_by_group"][handles["group"].id()] == expected_memberships[:2]
    assert [item["group_id"] for item in groups["groups_by_object"][handles["wall"].id()]] == [
        handles["group"].id(),
        handles["system"].id(),
        handles["distribution_system"].id(),
    ]
    assert groups["product_assignments"] == [
        {
            "relationship_id": handles["product_relationship"].id(),
            "product_id": handles["wall"].id(),
            "object_id": handles["space"].id(),
        }
    ]
    assert groups["products_by_object"] == {handles["space"].id(): [handles["wall"].id()]}
    assert groups["objects_by_product"] == {handles["wall"].id(): [handles["space"].id()]}


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_connection_feature_matrix_matches_ifcopenshell(schema: str) -> None:
    model, handles = connection_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    connections = data["connections"]

    assert actual_edges(data) == oracle_edges(model)
    assert connections["element_connections"] == [
        {
            "relationship_id": handles["element_relationship"].id(),
            "relationship_type": "IfcRelConnectsElements",
            "relating_element_id": handles["wall_a"].id(),
            "related_element_id": handles["wall_b"].id(),
            "connection_geometry_id": None,
            "relating_priorities": [],
            "related_priorities": [],
            "relating_connection_type": None,
            "related_connection_type": None,
        },
        {
            "relationship_id": handles["path_relationship"].id(),
            "relationship_type": "IfcRelConnectsPathElements",
            "relating_element_id": handles["wall_a"].id(),
            "related_element_id": handles["wall_b"].id(),
            "connection_geometry_id": None,
            "relating_priorities": [10, 20],
            "related_priorities": [30],
            "relating_connection_type": "ATSTART",
            "related_connection_type": "ATEND",
        },
    ]
    expected_relationship_ids = sorted(
        [handles["element_relationship"].id(), handles["path_relationship"].id()]
    )
    assert connections["connections_by_element"] == {
        handles["wall_a"].id(): expected_relationship_ids,
        handles["wall_b"].id(): expected_relationship_ids,
    }
    assert connections["ports"][handles["port_a"].id()]["flow_direction"] == "SOURCE"
    assert connections["ports"][handles["port_b"].id()]["flow_direction"] == "SINK"
    assert connections["ports_by_element"] == {
        handles["segment_a"].id(): [handles["port_a"].id()],
        handles["segment_b"].id(): [handles["port_b"].id()],
    }
    assert connections["elements_by_port"] == {
        handles["port_a"].id(): [handles["segment_a"].id()],
        handles["port_b"].id(): [handles["segment_b"].id()],
    }
    assert connections["port_connections"] == [
        {
            "relationship_id": handles["ports_relationship"].id(),
            "relating_port_id": handles["port_a"].id(),
            "related_port_id": handles["port_b"].id(),
            "realizing_element_id": handles["segment_a"].id(),
        }
    ]
    assert connections["connected_ports"] == {
        handles["port_a"].id(): [handles["port_b"].id()],
        handles["port_b"].id(): [handles["port_a"].id()],
    }
    boundaries = connections["space_boundaries"]
    assert [item["relationship_type"] for item in boundaries] == [
        "IfcRelSpaceBoundary",
        "IfcRelSpaceBoundary1stLevel",
        "IfcRelSpaceBoundary2ndLevel",
    ]
    assert boundaries[0]["physical_or_virtual"] == "PHYSICAL"
    assert boundaries[1]["internal_or_external"] == "EXTERNAL"
    assert boundaries[2]["parent_boundary_id"] == handles["boundary_first"].id()
    assert boundaries[2]["corresponding_boundary_id"] is None
    assert connections["boundaries_by_space"] == {
        handles["space"].id(): [
            handles["boundary"].id(),
            handles["boundary_first"].id(),
            handles["boundary_second"].id(),
        ]
    }


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_map_conversion_feature_matrix_matches_ifcopenshell(schema: str) -> None:
    model, handles = georeference_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    georef = data["georeferencing"]

    assert georef["has_georeference"] is True
    assert georef["source"] == "mapConversion"
    assert georef["map_conversion"] == {
        "express_id": handles["conversion"].id(),
        "ifc_type": "IfcMapConversion",
        "source_crs_id": handles["context"].id(),
        "target_crs_id": handles["crs"].id(),
        "eastings": 155000.0,
        "northings": 463000.0,
        "orthogonal_height": 1.5,
        "x_axis_abscissa": 0.0,
        "x_axis_ordinate": 1.0,
        "scale": 0.9999,
        "factor_x": None,
        "factor_y": None,
        "factor_z": None,
    }
    assert georef["projected_crs"] == {
        "express_id": handles["crs"].id(),
        "name": "EPSG:28992",
        "description": "Amersfoort / RD New",
        "geodetic_datum": "Amersfoort",
        "vertical_datum": "NAP",
        "map_projection": "Oblique Stereographic",
        "map_zone": "Netherlands",
        "map_unit_id": handles["map_unit"].id(),
        "map_unit": "mm",
        "map_unit_scale": pytest.approx(0.001),
    }
    assert georef["angle_to_grid_north"] == pytest.approx(90.0)
    matrix = georef["transform_matrix"]
    assert matrix[0] == pytest.approx(0.0, abs=1e-12)
    assert matrix[1] == pytest.approx(0.9999)
    assert matrix[4] == pytest.approx(-0.9999)
    assert matrix[10] == pytest.approx(0.9999)
    assert matrix[12:16] == pytest.approx([155000.0, 463000.0, 1.5, 1.0])


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_site_geolocation_fallback_matches_ifcopenshell(schema: str) -> None:
    model, handles = site_georeference_model(schema)
    data = ifx_core.model_data(as_bytes(model))
    georef = data["georeferencing"]
    conversion = georef["map_conversion"]

    assert georef["has_georeference"] is True
    assert georef["source"] == "siteLocation"
    assert conversion["express_id"] == handles["site"].id()
    assert conversion["eastings"] == pytest.approx(-74 - 5 / 60)
    assert conversion["northings"] == pytest.approx(4 + 36 / 60)
    assert conversion["orthogonal_height"] == 2600.0
    assert georef["projected_crs"]["name"] == "EPSG:4326"
    assert georef["transform_matrix"][12:15] == pytest.approx(
        [conversion["eastings"], conversion["northings"], 2600.0]
    )


@pytest.mark.parametrize(("schema", "expected_schema"), [("IFC4", "IFC4"), ("IFC4X3", "IFC4X3")])
@pytest.mark.parametrize(("prefix", "scale"), [(None, 1.0), ("MILLI", 0.001)])
def test_spatial_feature_matrix_matches_ifcopenshell(
    schema: str, expected_schema: str, prefix: str | None, scale: float
) -> None:
    model, handles = spatial_model(schema, prefix)
    data = ifx_core.model_data(as_bytes(model))
    spatial = data["spatial"]
    project_id = handles["project"].id()

    assert data["schema"] == expected_schema
    assert data["entity_count"] == len(list(model))
    assert data["length_unit_scale"] == pytest.approx(calculate_unit_scale(model))
    assert data["length_unit_scale"] == pytest.approx(scale)
    assert actual_edges(data) == oracle_edges(model)

    expected_children, attached = spatial_oracle(model, project_id)
    nodes = flatten_spatial(spatial["roots"])
    assert set(nodes) == attached
    assert spatial["project_id"] == project_id
    assert spatial["referenced_by_structure"] == reference_oracle(model)

    all_spatial_ids = {entity.id() for entity in model if is_spatial(entity)}
    assert spatial["orphan_spatial_ids"] == sorted(all_spatial_ids - attached)

    for express_id, node in nodes.items():
        entity = model.by_id(express_id)
        assert node["ifc_type"] == entity.is_a()
        assert node["global_id"] == getattr(entity, "GlobalId", None)
        assert node["name"] == (
            entity.Name or getattr(entity, "LongName", None) or f"Entity #{express_id}"
        )
        expected_long_name = getattr(entity, "LongName", None)
        if expected_long_name == node["name"]:
            expected_long_name = None
        assert node["long_name"] == expected_long_name
        assert [child["express_id"] for child in node["children"]] == sorted(
            expected_children[express_id]
        )
        assert node["elements"] == direct_elements(model, entity)
        assert node["referenced_elements"] == referenced_elements(model, entity)

    for storey in model.by_type("IfcBuildingStorey"):
        if storey.id() in attached:
            expected = get_storey_elevation(storey) * calculate_unit_scale(model)
            assert spatial["storey_elevations"][storey.id()] == pytest.approx(expected)

    category_maps = {
        "by_site": {"IfcSite"},
        "by_building": {
            "IfcBuilding",
            "IfcFacility",
            "IfcBridge",
            "IfcRoad",
            "IfcRailway",
            "IfcMarineFacility",
        },
        "by_storey": {"IfcBuildingStorey"},
        "by_space": {"IfcSpace", "IfcSpatialZone"},
    }
    for output_name, ifc_types in category_maps.items():
        expected = {
            entity.id(): direct_elements(model, entity)
            for entity in model
            if entity.id() in attached and entity.is_a() in ifc_types
        }
        assert spatial[output_name] == expected

    for element_id, container_id in spatial["element_to_container"].items():
        oracle = get_container(model.by_id(element_id))
        assert oracle is not None
        assert oracle.id() == container_id
    for element_id, storey_id in spatial["element_to_storey"].items():
        entity = model.by_id(element_id)
        if is_spatial(entity):
            decomposes = getattr(entity, "Decomposes", ())
            oracle = decomposes[0].RelatingObject if decomposes else None
        else:
            oracle = get_container(entity)
        while oracle is not None and not oracle.is_a("IfcBuildingStorey"):
            decomposes = getattr(oracle, "Decomposes", ())
            oracle = decomposes[0].RelatingObject if decomposes else get_container(oracle)
        assert oracle is not None
        assert oracle.id() == storey_id


def expected_material(
    definition: Any, scale: float, source_id: int | None = None
) -> dict[str, Any]:
    if definition.is_a() == "IfcMaterialLayerSetUsage":
        return expected_material(definition.ForLayerSet, scale, definition.id())
    if definition.is_a() == "IfcMaterialProfileSetUsage":
        return expected_material(definition.ForProfileSet, scale, definition.id())

    result: dict[str, Any] = {
        "source_definition_id": source_id or definition.id(),
        "resolved_definition_id": definition.id(),
        "material_type": definition.is_a().removeprefix("Ifc"),
        "name": None,
        "description": None,
        "category": None,
        "layers": [],
        "profiles": [],
        "constituents": [],
        "materials": [],
    }
    if definition.is_a() == "IfcMaterial":
        result.update(
            name=definition.Name,
            description=definition.Description,
            category=definition.Category,
        )
    elif definition.is_a() == "IfcMaterialLayerSet":
        result.update(name=definition.LayerSetName, description=definition.Description)
        result["layers"] = [
            {
                "express_id": layer.id(),
                "material_id": layer.Material.id() if layer.Material else None,
                "material_name": layer.Material.Name if layer.Material else None,
                "material_category": layer.Material.Category if layer.Material else None,
                "thickness": layer.LayerThickness * scale,
                "is_ventilated": layer.IsVentilated,
                "name": layer.Name,
                "description": layer.Description,
                "category": layer.Category,
                "priority": layer.Priority,
            }
            for layer in definition.MaterialLayers
        ]
    elif definition.is_a() == "IfcMaterialProfileSet":
        result.update(name=definition.Name, description=definition.Description)
        result["profiles"] = [
            {
                "express_id": profile.id(),
                "material_id": profile.Material.id() if profile.Material else None,
                "material_name": profile.Material.Name if profile.Material else None,
                "material_category": profile.Material.Category if profile.Material else None,
                "profile_id": profile.Profile.id() if profile.Profile else None,
                "name": profile.Name,
                "description": profile.Description,
                "category": profile.Category,
                "priority": profile.Priority,
            }
            for profile in definition.MaterialProfiles
        ]
    elif definition.is_a() == "IfcMaterialConstituentSet":
        result.update(name=definition.Name, description=definition.Description)
        result["constituents"] = [
            {
                "express_id": constituent.id(),
                "material_id": constituent.Material.id() if constituent.Material else None,
                "material_name": constituent.Material.Name if constituent.Material else None,
                "material_category": constituent.Material.Category
                if constituent.Material
                else None,
                "name": constituent.Name,
                "description": constituent.Description,
                "fraction": constituent.Fraction,
                "category": constituent.Category,
            }
            for constituent in definition.MaterialConstituents
        ]
    elif definition.is_a() == "IfcMaterialList":
        result["materials"] = [
            {
                "express_id": material.id(),
                "name": material.Name or f"Material #{material.id()}",
                "category": material.Category,
            }
            for material in definition.Materials
        ]
    else:  # pragma: no cover - the test's supported-type set controls this
        raise AssertionError(definition.is_a())
    return result


def material_leaf_ids(material: dict[str, Any]) -> list[int]:
    if material["material_type"] == "Material":
        return [material["resolved_definition_id"]]
    if material["material_type"] == "MaterialLayerSet":
        return [item["material_id"] for item in material["layers"] if item["material_id"]]
    if material["material_type"] == "MaterialProfileSet":
        return [item["material_id"] for item in material["profiles"] if item["material_id"]]
    if material["material_type"] == "MaterialConstituentSet":
        return [item["material_id"] for item in material["constituents"] if item["material_id"]]
    if material["material_type"] == "MaterialList":
        return [item["express_id"] for item in material["materials"]]
    raise AssertionError(material["material_type"])


@pytest.mark.parametrize("schema", ["IFC4", "IFC4X3"])
def test_material_feature_matrix_matches_ifcopenshell(schema: str) -> None:
    model, handles = material_model(schema)
    source = as_bytes(model)
    data = ifx_core.model_data(source)
    materials = data["materials"]
    scale = calculate_unit_scale(model)

    assert actual_edges(data) == oracle_edges(model)

    expected_definition_ids = {
        entity.id() for entity in model if entity.is_a() in MATERIAL_DEFINITION_TYPES
    }
    assert set(materials["definitions"]) == expected_definition_ids
    for definition_id, actual in materials["definitions"].items():
        assert actual == expected_material(model.by_id(definition_id), scale)

    expected_associations = [
        {
            "relationship_id": relationship.id(),
            "relating_material_id": relationship.RelatingMaterial.id(),
            "related_objects": [entity.id() for entity in relationship.RelatedObjects],
        }
        for relationship in sorted(
            model.by_type("IfcRelAssociatesMaterial"), key=lambda entity: entity.id()
        )
    ]
    assert materials["associations"] == expected_associations

    # IfcOpenShell is the semantic oracle whenever an element has one effective
    # assignment. Multiple direct associations are checked independently below.
    multiple_id = handles["multiple"].id()
    for element_id, assignments in materials["element_materials"].items():
        if element_id == multiple_id:
            continue
        element = model.by_id(element_id)
        oracle = get_material(element, should_skip_usage=False, should_inherit=True)
        assert oracle is not None
        assert len(assignments) == 1
        assert assignments[0]["definition_id"] == oracle.id()
        assert material_leaf_ids(assignments[0]["material"]) == [
            material.id() for material in get_materials(element)
        ]

    multiple = materials["element_materials"][multiple_id]
    assert [assignment["definition_id"] for assignment in multiple] == [
        handles["steel"].id(),
        handles["concrete"].id(),
    ]
    assert all(assignment["inherited_from_type"] is None for assignment in multiple)

    inherited = materials["element_materials"][handles["elements"][7].id()][0]
    assert inherited["definition_id"] == handles["insulation"].id()
    assert inherited["inherited_from_type"] == handles["wall_type"].id()

    assert json.loads(ifx_core.model_data_json(source)) == json_compatible(data)
    assert ifx_core.model_data(source) == data


def test_ifc2x3_is_supported() -> None:
    model = ifcopenshell.file(schema="IFC2X3")
    model.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Legacy project")
    data = ifx_core.model_data(as_bytes(model))
    assert data["schema"] == "IFC2X3"
    assert data["spatial"]["roots"][0]["name"] == "Legacy project"
