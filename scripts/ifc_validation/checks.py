import math
from collections import Counter

import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.unit
import numpy as np

from .mesh import Tolerances, compare_metrics, mesh_metrics
from .property_reference import matches, property_sets, unset

RELATIONS = {
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
COMMON = {
    "id",
    "type",
    "GlobalId",
    "OwnerHistory",
    "Name",
    "Description",
    "ObjectType",
    "ObjectPlacement",
    "Representation",
}


class Findings:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.example_counts: Counter[str] = Counter()
        self.examples: list[dict[str, object]] = []

    def add(self, check: str, element_id: int, detail: object) -> None:
        self.counts[check] += 1
        if len(self.examples) < 200 and self.example_counts[check] < 20:
            self.example_counts[check] += 1
            self.examples.append({"check": check, "element_id": element_id, "detail": detail})

    def result(self, **counts: object) -> dict[str, object]:
        return {
            "status": "fail" if self.counts else "pass",
            **counts,
            "failure_counts": dict(sorted(self.counts.items())),
            "examples": self.examples,
            "examples_truncated": sum(self.counts.values()) > len(self.examples),
        }


def same_value(expected: object, actual: object) -> bool:
    if isinstance(expected, bool):
        return str(actual).lower() == str(expected).lower()
    if isinstance(expected, (int, float)):
        try:
            return math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=5.1e-7)
        except (TypeError, ValueError):
            return False
    return str(expected) == str(actual)


def relationships(model: object) -> set[tuple[str, int, int, int]]:
    expected: set[tuple[str, int, int, int]] = set()
    for relation in model.by_type("IfcRelationship"):
        attributes = RELATIONS.get(relation.is_a())
        if attributes is None:
            continue
        left, right = (getattr(relation, attribute) for attribute in attributes)
        lefts = left if isinstance(left, tuple) else (left,)
        rights = right if isinstance(right, tuple) else (right,)
        for parent in lefts:
            for child in rights:
                if parent is not None and child is not None:
                    expected.add((relation.is_a().upper(), relation.id(), parent.id(), child.id()))
    return expected


def check_model(model: object, data: dict[str, object]) -> dict[str, object]:
    issues = Findings()
    family = "IFC4X3" if model.schema.startswith("IFC4X3") else model.schema
    if data["schema"] != family:
        issues.add("schema", 0, {"expected": family, "actual": data["schema"]})
    if data["entity_count"] != sum(1 for _ in model):
        issues.add("entity_count", 0, data["entity_count"])
    scale = ifcopenshell.util.unit.calculate_unit_scale(model)
    if not same_value(scale, data["length_unit_scale"]):
        issues.add("length_unit_scale", 0, data["length_unit_scale"])
    actual = {
        (
            edge["relationship_type"].upper(),
            edge["relationship_id"],
            edge["relating_id"],
            edge["related_id"],
        )
        for edge in data["relationships"]["edges"]
    }
    expected = relationships(model)
    for edge in sorted(expected - actual):
        issues.add("missing_relationship", edge[1], edge)
    for edge in sorted(actual - expected):
        issues.add("extra_relationship", edge[1], edge)
    containers = data["spatial"]["element_to_container"]
    for element in model.by_type("IfcElement"):
        expected_container = ifcopenshell.util.element.get_container(element)
        actual_container = containers.get(element.id())
        if expected_container is not None and actual_container != expected_container.id():
            issues.add("spatial_container", element.id(), actual_container)
        elif expected_container is None and actual_container is not None:
            issues.add("unexpected_spatial_container", element.id(), actual_container)
        material = ifcopenshell.util.element.get_material(
            element, should_skip_usage=False, should_inherit=True
        )
        assignments = data["materials"]["element_materials"].get(element.id(), [])
        if material is not None and material.id() not in {
            row["definition_id"] for row in assignments
        }:
            issues.add("missing_material_assignment", element.id(), material.id())
        if material is None and assignments:
            issues.add("unexpected_material_assignment", element.id(), assignments)
    unchecked = Counter(
        relation.is_a()
        for relation in model.by_type("IfcRelationship")
        if relation.is_a() not in RELATIONS
    )
    return issues.result(
        expected_relationships=len(expected),
        actual_relationships=len(actual),
        relationship_types_outside_contract=dict(sorted(unchecked.items())),
    )


def check_entities(model: object, data: dict[str, object]) -> dict[str, object]:
    issues = Findings()
    expected = {entity.id(): entity for entity in model.by_type("IfcProduct")}
    actual = data["entities"]
    for element_id in sorted(expected.keys() - actual.keys()):
        issues.add("missing_product_metadata", element_id, expected[element_id].is_a())
    for element_id, row in actual.items():
        entity = model.by_id(element_id)
        if element_id not in expected and not entity.is_a("IfcTypeProduct"):
            issues.add("extra_product_metadata", element_id, row["ifc_type"])
        for field, source_field in (
            ("ifc_type", "type"),
            ("global_id", "GlobalId"),
            ("name", "Name"),
            ("description", "Description"),
            ("object_type", "ObjectType"),
        ):
            value = entity.is_a() if source_field == "type" else getattr(entity, source_field, None)
            if row.get(field) != (value or None):
                issues.add(
                    f"identity.{field}", element_id, {"expected": value, "actual": row.get(field)}
                )
        attributes = {item["name"]: item["value"] for item in row["attributes"]}
        expected_attributes = {
            key: value
            for key, value in entity.get_info().items()
            if key not in COMMON and isinstance(value, (str, int, float, bool))
        }
        for key, value in expected_attributes.items():
            if key not in attributes or not same_value(value, attributes[key]):
                issues.add(
                    "attribute_value",
                    element_id,
                    {"name": key, "expected": value, "actual": attributes.get(key)},
                )
        for key in attributes.keys() - expected_attributes.keys():
            issues.add("extra_attribute", element_id, key)
        expected_properties = property_sets(entity)
        actual_properties = {
            item["name"]: {prop["name"]: prop for prop in item["properties"]}
            for item in row["property_sets"]
        }
        for set_name, values in expected_properties.items():
            for name, prop in values.items():
                candidate = actual_properties.get(set_name, {}).get(name)
                if candidate is None and unset(prop):
                    continue
                if candidate is None or not matches(prop, candidate, same_value):
                    issues.add(
                        "property_sets",
                        element_id,
                        {
                            "name": f"{set_name}.{name}",
                            "property_type": prop.is_a(),
                            "actual": candidate,
                        },
                    )
        for set_name, values in actual_properties.items():
            for name in values:
                if name not in expected_properties.get(set_name, {}):
                    issues.add("extra_property_sets", element_id, f"{set_name}.{name}")
        for sets_key, properties_key, option in (("quantity_sets", "quantities", "qtos_only"),):
            expected_sets = ifcopenshell.util.element.get_psets(
                entity, should_inherit=True, **{option: True}
            )
            actual_sets = {
                item["name"]: {prop["name"]: prop["value"] for prop in item[properties_key]}
                for item in row[sets_key]
            }
            for name, values in expected_sets.items():
                for key, value in values.items():
                    if key == "id":
                        continue
                    candidate = actual_sets.get(name, {}).get(key)
                    if value is None and sets_key == "property_sets":
                        if candidate is not None:
                            issues.add(
                                sets_key,
                                element_id,
                                {
                                    "name": f"{name}.{key}",
                                    "expected": None,
                                    "actual": candidate,
                                },
                            )
                        continue
                    if not isinstance(value, (str, int, float, bool)):
                        issues.add("uncompared_complex_property", element_id, f"{name}.{key}")
                    elif candidate is None or not same_value(value, candidate):
                        issues.add(
                            sets_key,
                            element_id,
                            {"name": f"{name}.{key}", "expected": value, "actual": candidate},
                        )
            for name, values in actual_sets.items():
                for key in values:
                    if key not in expected_sets.get(name, {}):
                        issues.add(f"extra_{sets_key}", element_id, f"{name}.{key}")
    if not same_value(
        ifcopenshell.util.unit.calculate_unit_scale(model), data["length_unit_scale"]
    ):
        issues.add("length_unit_scale", 0, data["length_unit_scale"])
    return issues.result(expected_products=len(expected), actual_rows=len(actual))


def geometry_products(model: object) -> tuple[list[object], dict[str, list[int]]]:
    included: list[object] = []
    exclusions: dict[str, list[int]] = {}
    for product in model.by_type("IfcProduct"):
        representation = getattr(product, "Representation", None)
        if representation is None:
            reason = "no representation"
        elif not any(
            getattr(item, "RepresentationIdentifier", None) in (None, "", "Body", "Facetation")
            and getattr(getattr(item, "ContextOfItems", None), "CoordinateSpaceDimension", 3) == 3
            for item in representation.Representations
        ):
            reason = "no 3D Body or Facetation representation"
        else:
            included.append(product)
            continue
        exclusions.setdefault(reason, []).append(product.id())
    return included, exclusions


def reference_geometry(model: object, products: list[object]) -> dict[int, dict[str, object]]:
    if not products:
        return {}
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    settings.set("disable-opening-subtractions", False)
    iterator = ifcopenshell.geom.iterator(settings, model, 1, include=products)
    result: dict[int, dict[str, object]] = {}
    if iterator.initialize():
        while True:
            shape = iterator.get()
            result[shape.id] = mesh_metrics(
                np.array(shape.geometry.verts, dtype=np.float64).reshape(-1, 3),
                np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3),
            )
            if not iterator.next():
                break
    return result


def check_geometry(
    model: object,
    data: dict[str, object],
    reference: dict[int, dict[str, object]],
    limits: Tolerances,
    analytic: dict[str, object] | None = None,
) -> dict[str, object]:
    issues = Findings()
    products, exclusions = geometry_products(model)
    represented = {product.id() for product in products}
    actual = data["elements"]
    if data.get("up_axis") != "Z" or data.get("units") != "m":
        issues.add(
            "coordinate_contract", 0, {"up_axis": data.get("up_axis"), "units": data.get("units")}
        )
    if data.get("element_count") != len(actual):
        issues.add("element_count", 0, data.get("element_count"))
    for element_id in sorted(represented - reference.keys()):
        issues.add("reference_geometry_missing", element_id, model.by_id(element_id).is_a())
    for element_id in sorted(reference.keys() - actual.keys()):
        issues.add("candidate_geometry_missing", element_id, model.by_id(element_id).is_a())
    # Keep every extra ID visible. An output outside this comparison profile
    # requires a documented decision; it must not disappear from the report.
    for element_id in sorted(actual.keys() - reference.keys()):
        issues.add("candidate_geometry_extra", element_id, actual[element_id]["ifc_type"])
    compared = 0
    for element_id, mesh in actual.items():
        try:
            metrics = mesh_metrics(
                np.frombuffer(mesh["vertices"], dtype="<f8").reshape(-1, 3),
                np.frombuffer(mesh["faces"], dtype="<u4").reshape(-1, 3),
            )
        except (ValueError, TypeError) as error:
            issues.add("invalid_mesh", element_id, str(error))
            continue
        if element_id in reference:
            compared += 1
            for failure in compare_metrics(reference[element_id], metrics, limits):
                issues.add(
                    "geometry_difference",
                    element_id,
                    {
                        "reason": failure,
                        "reference": reference[element_id],
                        "candidate": metrics,
                    },
                )
        if analytic is not None and element_id == analytic["element_id"]:
            for failure in compare_metrics(analytic, metrics, limits):
                issues.add("analytic_geometry_difference", element_id, failure)
        try:
            entity = model.by_id(element_id)
            if mesh["ifc_type"] != entity.is_a() or mesh.get("global_id") != getattr(
                entity, "GlobalId", None
            ):
                issues.add("geometry_identity", element_id, mesh["ifc_type"])
        except RuntimeError:
            issues.add("unknown_geometry_id", element_id, mesh["ifc_type"])
    return issues.result(
        represented_products=len(represented),
        reference_meshes=len(reference),
        candidate_meshes=len(actual),
        compared_meshes=compared,
        expected_exclusions=exclusions,
        empty_model=not represented,
        reference_open_meshes=[key for key, metrics in reference.items() if not metrics["closed"]],
    )
