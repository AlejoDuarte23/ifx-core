import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

import ifx_core

try:
    import ifcopenshell
    from ifcopenshell.util.element import get_container, get_material, get_materials
    from ifcopenshell.util.unit import calculate_unit_scale
except ModuleNotFoundError:
    pytest.skip("IfcOpenShell is required for parity tests", allow_module_level=True)


def fixture_path() -> Path:
    configured = os.environ.get("IFX_PARITY_MODEL")
    if not configured:
        pytest.skip("set IFX_PARITY_MODEL to the requested IFC comparison fixture")
    path = Path(configured)
    if not path.is_file():
        pytest.skip("set IFX_PARITY_MODEL to the requested IFC comparison fixture")
    return path


@pytest.fixture(scope="module")
def compared() -> tuple[Any, dict[str, Any]]:
    path = fixture_path()
    source = path.read_bytes()
    return ifcopenshell.open(path), ifx_core.model_data(source)


RELATIONSHIP_ATTRIBUTES = {
    "IfcRelAggregates": ("RelatingObject", "RelatedObjects"),
    "IfcRelNests": ("RelatingObject", "RelatedObjects"),
    "IfcRelContainedInSpatialStructure": ("RelatingStructure", "RelatedElements"),
    "IfcRelReferencedInSpatialStructure": ("RelatingStructure", "RelatedElements"),
    "IfcRelDefinesByType": ("RelatingType", "RelatedObjects"),
    "IfcRelDefinesByProperties": ("RelatingPropertyDefinition", "RelatedObjects"),
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


def entity_list(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    return value if isinstance(value, tuple) else (value,)


def oracle_edges(model: Any, relation_type: str) -> set[tuple[int, int, int]]:
    relating_attr, related_attr = RELATIONSHIP_ATTRIBUTES[relation_type]

    result = set()
    for relationship in model.by_type(relation_type):
        if relationship.is_a() != relation_type:
            continue
        relating_entities = entity_list(getattr(relationship, relating_attr))
        related_entities = entity_list(getattr(relationship, related_attr))
        result.update(
            (relationship.id(), relating.id(), related.id())
            for relating in relating_entities
            for related in related_entities
        )
    return result


def assert_relationship_parity(model: Any, data: dict[str, Any]) -> None:
    ours: dict[str, set[tuple[int, int, int]]] = defaultdict(set)
    for edge in data["relationships"]["edges"]:
        ours[edge["relationship_type"]].add(
            (edge["relationship_id"], edge["relating_id"], edge["related_id"])
        )

    for relation_type in RELATIONSHIP_ATTRIBUTES:
        assert ours[relation_type] == oracle_edges(model, relation_type)


def assert_opening_parity(model: Any, data: dict[str, Any]) -> None:
    openings = data["openings"]
    expected_voids = [
        {
            "relationship_id": relationship.id(),
            "element_id": relationship.RelatingBuildingElement.id(),
            "opening_id": relationship.RelatedOpeningElement.id(),
        }
        for relationship in sorted(model.by_type("IfcRelVoidsElement"), key=lambda item: item.id())
    ]
    expected_fills = [
        {
            "relationship_id": relationship.id(),
            "opening_id": relationship.RelatingOpeningElement.id(),
            "filling_id": relationship.RelatedBuildingElement.id(),
        }
        for relationship in sorted(model.by_type("IfcRelFillsElement"), key=lambda item: item.id())
    ]
    assert openings["voids"] == expected_voids
    assert openings["fills"] == expected_fills

    expected_openings_by_element: dict[int, list[int]] = defaultdict(list)
    expected_elements_by_opening: dict[int, list[int]] = defaultdict(list)
    for relationship in expected_voids:
        expected_openings_by_element[relationship["element_id"]].append(relationship["opening_id"])
        expected_elements_by_opening[relationship["opening_id"]].append(relationship["element_id"])
    expected_fillings_by_opening: dict[int, list[int]] = defaultdict(list)
    expected_openings_by_filling: dict[int, list[int]] = defaultdict(list)
    for relationship in expected_fills:
        expected_fillings_by_opening[relationship["opening_id"]].append(relationship["filling_id"])
        expected_openings_by_filling[relationship["filling_id"]].append(relationship["opening_id"])
    assert openings["openings_by_element"] == {
        key: sorted(set(values)) for key, values in expected_openings_by_element.items()
    }
    assert openings["elements_by_opening"] == {
        key: sorted(set(values)) for key, values in expected_elements_by_opening.items()
    }
    assert openings["fillings_by_opening"] == {
        key: sorted(set(values)) for key, values in expected_fillings_by_opening.items()
    }
    assert openings["openings_by_filling"] == {
        key: sorted(set(values)) for key, values in expected_openings_by_filling.items()
    }


def assert_spatial_parity(model: Any, data: dict[str, Any]) -> None:
    spatial = data["spatial"]
    assert data["schema"] in {"IFC4", "IFC4X3"}
    assert data["entity_count"] == len(list(model))
    assert data["length_unit_scale"] == pytest.approx(calculate_unit_scale(model))
    assert spatial["project_id"] == model.by_type("IfcProject")[0].id()
    assert spatial["orphan_spatial_ids"] == []

    map_by_type = {
        "IfcSite": spatial["by_site"],
        "IfcBuilding": spatial["by_building"],
        "IfcBuildingStorey": spatial["by_storey"],
        "IfcSpace": spatial["by_space"],
    }
    for ifc_type, actual in map_by_type.items():
        expected: dict[int, list[int]] = {}
        for structure in model.by_type(ifc_type):
            direct = sorted(
                element.id()
                for relationship in getattr(structure, "ContainsElements", ())
                for element in relationship.RelatedElements
                if not element.is_a("IfcSpatialElement")
            )
            expected[structure.id()] = direct
        assert actual == expected

    # IFClite-compatible reverse maps intentionally cover direct containment
    # plus aggregate/nest descendants. IfcOpenShell additionally resolves
    # opening/filling ancestry; every mapping we emit must agree with its more
    # expansive get_container oracle.
    for element_id, container_id in spatial["element_to_container"].items():
        element = model.by_id(element_id)
        if not element or not element.is_a("IfcElement"):
            continue
        oracle = get_container(element)
        assert oracle is not None
        assert oracle.id() == container_id


def resolved_leaf_ids(material: dict[str, Any]) -> list[int]:
    material_type = material["material_type"]
    if material_type == "Material":
        return [material["resolved_definition_id"]]
    if material_type == "MaterialLayerSet":
        return [item["material_id"] for item in material["layers"] if item["material_id"]]
    if material_type == "MaterialProfileSet":
        return [item["material_id"] for item in material["profiles"] if item["material_id"]]
    if material_type == "MaterialConstituentSet":
        return [item["material_id"] for item in material["constituents"] if item["material_id"]]
    if material_type == "MaterialList":
        return [item["express_id"] for item in material["materials"]]
    raise AssertionError(material_type)


def assert_material_parity(model: Any, data: dict[str, Any]) -> None:
    assignments = data["materials"]["element_materials"]
    oracle_assigned = {
        element.id(): get_material(element, should_skip_usage=False, should_inherit=True)
        for element in model.by_type("IfcElement")
    }
    oracle_assigned = {key: value for key, value in oracle_assigned.items() if value is not None}

    assert set(assignments) == set(oracle_assigned)
    for element_id, oracle_material in oracle_assigned.items():
        actual = assignments[element_id]
        assert actual[0]["definition_id"] == oracle_material.id()
        assert resolved_leaf_ids(actual[0]["material"]) == [
            material.id() for material in get_materials(model.by_id(element_id))
        ]


def exact_entities(model: Any, ifc_type: str) -> list[Any]:
    try:
        entities = model.by_type(ifc_type)
    except RuntimeError:
        return []
    return [entity for entity in entities if entity.is_a() == ifc_type]


def association_rows(model: Any, ifc_type: str, relating_attribute: str) -> list[dict[str, Any]]:
    key = "classification_id" if ifc_type == "IfcRelAssociatesClassification" else "document_id"
    return [
        {
            "relationship_id": relationship.id(),
            key: getattr(relationship, relating_attribute).id(),
            "related_objects": [entity.id() for entity in relationship.RelatedObjects],
        }
        for relationship in sorted(exact_entities(model, ifc_type), key=lambda item: item.id())
    ]


def expected_inherited_assignments(
    model: Any, association_type: str, relating_attribute: str
) -> dict[int, list[tuple[int, int | None]]]:
    own: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for relationship in sorted(exact_entities(model, association_type), key=lambda item: item.id()):
        definition_id = getattr(relationship, relating_attribute).id()
        for entity in relationship.RelatedObjects:
            own[entity.id()].append((relationship.id(), definition_id))

    type_by_object: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for relationship in sorted(
        exact_entities(model, "IfcRelDefinesByType"), key=lambda item: item.id()
    ):
        for entity in relationship.RelatedObjects:
            type_by_object[entity.id()].append((relationship.id(), relationship.RelatingType.id()))

    candidate_ids = {
        entity_id
        for entity_id in own
        if not (
            model.by_id(entity_id).is_a().endswith("Type")
            or model.by_id(entity_id).is_a().endswith("Style")
        )
    } | set(type_by_object)
    expected: dict[int, list[tuple[int, int | None]]] = {}
    for entity_id in candidate_ids:
        rows: list[tuple[int, int | None]] = []
        seen: set[int] = set()
        for _, definition_id in own.get(entity_id, []):
            if definition_id not in seen:
                seen.add(definition_id)
                rows.append((definition_id, None))
        for _, type_id in type_by_object.get(entity_id, []):
            for _, definition_id in own.get(type_id, []):
                if definition_id not in seen:
                    seen.add(definition_id)
                    rows.append((definition_id, type_id))
        if rows:
            expected[entity_id] = rows
    return expected


def assert_classification_parity(model: Any, data: dict[str, Any]) -> None:
    classifications = data["classifications"]
    assert set(classifications["systems"]) == {
        entity.id() for entity in exact_entities(model, "IfcClassification")
    }
    assert set(classifications["references"]) == {
        entity.id() for entity in exact_entities(model, "IfcClassificationReference")
    }
    assert classifications["associations"] == association_rows(
        model, "IfcRelAssociatesClassification", "RelatingClassification"
    )
    expected = expected_inherited_assignments(
        model, "IfcRelAssociatesClassification", "RelatingClassification"
    )
    actual = {
        entity_id: [(row["classification_id"], row["inherited_from_type"]) for row in assignments]
        for entity_id, assignments in classifications["element_classifications"].items()
    }
    assert actual == expected


def assert_document_parity(model: Any, data: dict[str, Any]) -> None:
    documents = data["documents"]
    expected_definition_ids = {
        entity.id()
        for ifc_type in ("IfcDocumentInformation", "IfcDocumentReference")
        for entity in exact_entities(model, ifc_type)
    }
    assert set(documents["definitions"]) == expected_definition_ids
    assert documents["associations"] == association_rows(
        model, "IfcRelAssociatesDocument", "RelatingDocument"
    )
    expected = expected_inherited_assignments(model, "IfcRelAssociatesDocument", "RelatingDocument")
    actual = {
        entity_id: [(row["definition_id"], row["inherited_from_type"]) for row in assignments]
        for entity_id, assignments in documents["element_documents"].items()
    }
    assert actual == expected


def assert_group_parity(model: Any, data: dict[str, Any]) -> None:
    groups = data["groups"]
    expected_memberships = []
    for relation_type in ("IfcRelAssignsToGroup", "IfcRelAssignsToGroupByFactor"):
        for relationship in exact_entities(model, relation_type):
            factor = getattr(relationship, "Factor", None)
            expected_memberships.extend(
                {
                    "relationship_id": relationship.id(),
                    "group_id": relationship.RelatingGroup.id(),
                    "object_id": entity.id(),
                    "factor": factor,
                }
                for entity in relationship.RelatedObjects
            )
    expected_memberships.sort(key=lambda row: (row["relationship_id"], row["object_id"]))
    assert groups["memberships"] == expected_memberships

    expected_products = [
        {
            "relationship_id": relationship.id(),
            "product_id": relationship.RelatingProduct.id(),
            "object_id": entity.id(),
        }
        for relationship in exact_entities(model, "IfcRelAssignsToProduct")
        for entity in relationship.RelatedObjects
    ]
    expected_products.sort(key=lambda row: (row["relationship_id"], row["object_id"]))
    assert groups["product_assignments"] == expected_products


def assert_connection_parity(model: Any, data: dict[str, Any]) -> None:
    connections = data["connections"]
    expected_element_ids = {
        relationship.id()
        for relation_type in ("IfcRelConnectsElements", "IfcRelConnectsPathElements")
        for relationship in exact_entities(model, relation_type)
    }
    assert {row["relationship_id"] for row in connections["element_connections"]} == (
        expected_element_ids
    )
    expected_port_elements = {
        relationship.id() for relationship in exact_entities(model, "IfcRelConnectsPortToElement")
    }
    assert {row["relationship_id"] for row in connections["port_to_element"]} == (
        expected_port_elements
    )
    expected_ports = {
        relationship.id() for relationship in exact_entities(model, "IfcRelConnectsPorts")
    }
    assert {row["relationship_id"] for row in connections["port_connections"]} == expected_ports
    expected_boundaries = {
        relationship.id()
        for relation_type in (
            "IfcRelSpaceBoundary",
            "IfcRelSpaceBoundary1stLevel",
            "IfcRelSpaceBoundary2ndLevel",
        )
        for relationship in exact_entities(model, relation_type)
    }
    assert {row["relationship_id"] for row in connections["space_boundaries"]} == (
        expected_boundaries
    )


def assert_georeferencing_parity(model: Any, data: dict[str, Any]) -> None:
    georef = data["georeferencing"]
    conversions = sorted(
        [
            *exact_entities(model, "IfcMapConversion"),
            *exact_entities(model, "IfcMapConversionScaled"),
        ],
        key=lambda entity: entity.id(),
    )
    projected = sorted(exact_entities(model, "IfcProjectedCRS"), key=lambda entity: entity.id())
    if conversions:
        expected = conversions[0]
        actual = georef["map_conversion"]
        assert georef["source"] == "mapConversion"
        assert actual["express_id"] == expected.id()
        assert actual["eastings"] == pytest.approx(expected.Eastings)
        assert actual["northings"] == pytest.approx(expected.Northings)
        assert actual["orthogonal_height"] == pytest.approx(expected.OrthogonalHeight)
        if expected.Scale is None:
            assert actual["scale"] is None
        else:
            assert actual["scale"] == pytest.approx(expected.Scale)
    if projected:
        assert georef["projected_crs"]["express_id"] == projected[0].id()
        assert georef["projected_crs"]["name"] == projected[0].Name
    if conversions or projected:
        assert georef["has_georeference"] is True


@pytest.mark.integration
def test_relationship_edges_exactly_match_ifcopenshell(
    compared: tuple[Any, dict[str, Any]],
) -> None:
    assert_relationship_parity(*compared)


@pytest.mark.integration
def test_spatial_results_match_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_spatial_parity(*compared)


@pytest.mark.integration
def test_material_resolution_matches_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_material_parity(*compared)


@pytest.mark.integration
def test_opening_resolution_matches_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_opening_parity(*compared)


@pytest.mark.integration
def test_classifications_match_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_classification_parity(*compared)


@pytest.mark.integration
def test_documents_match_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_document_parity(*compared)


@pytest.mark.integration
def test_groups_match_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_group_parity(*compared)


@pytest.mark.integration
def test_connections_match_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_connection_parity(*compared)


@pytest.mark.integration
def test_georeferencing_matches_ifcopenshell(compared: tuple[Any, dict[str, Any]]) -> None:
    assert_georeferencing_parity(*compared)
