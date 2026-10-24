from collections.abc import Callable

import ifcopenshell
import ifcopenshell.util.element


def atom(value: object) -> object:
    if isinstance(value, ifcopenshell.entity_instance) and hasattr(value, "wrappedValue"):
        result = value.wrappedValue
        if value.is_a().upper() == "IFCLOGICAL" and result == "UNKNOWN":
            return "unknown"
        return result
    return value


def property_sets(entity: object) -> dict[str, dict[str, object]]:
    sets: dict[str, dict[str, object]] = {}
    definitions: list[object] = []
    inherited = ifcopenshell.util.element.get_type(entity)
    if inherited is not None and inherited != entity:
        definitions.extend(getattr(inherited, "HasPropertySets", ()) or ())
    definitions.extend(getattr(entity, "HasPropertySets", ()) or ())
    for relation in getattr(entity, "IsDefinedBy", ()) or ():
        if relation.is_a("IfcRelDefinesByProperties"):
            definition = relation.RelatingPropertyDefinition
            if definition.is_a("IfcPropertySetDefinitionSet"):
                definitions.extend(definition.wrappedValue)
            else:
                definitions.append(definition)
    for definition in definitions:
        if not definition.is_a("IfcPropertySet"):
            continue
        members = sets.setdefault(definition.Name or "", {})
        for prop in definition.HasProperties or ():
            if prop.Name:
                members[prop.Name] = prop
    return sets


def matches(
    reference: object,
    actual: dict[str, object],
    compare: Callable[[object, object], bool],
    path: set[int] | None = None,
) -> bool:
    if actual.get("issue"):
        return False
    path = set() if path is None else path
    if reference.id() in path:
        return False
    path = path | {reference.id()}
    kind = reference.is_a()
    details = actual.get("details", {})
    unit = getattr(reference, "Unit", None)
    if kind == "IfcPropertyEnumeratedValue" and reference.EnumerationReference is not None:
        unit = reference.EnumerationReference.Unit
    if actual.get("unit_id") != (unit.id() if unit is not None else None):
        return False
    if kind == "IfcPropertySingleValue":
        expected = atom(reference.NominalValue)
        return expected is None or compare(expected, actual["value"])
    if kind in ("IfcPropertyListValue", "IfcPropertyEnumeratedValue"):
        values = (
            reference.ListValues if kind == "IfcPropertyListValue" else reference.EnumerationValues
        )
        expected_kind = "list" if kind == "IfcPropertyListValue" else "enumerated"
        candidates = details.get("values", [])
        if kind == "IfcPropertyEnumeratedValue":
            enumeration = reference.EnumerationReference
            if details.get("enumeration_id") != (enumeration.id() if enumeration else None):
                return False
        return (
            details.get("kind") == expected_kind
            and len(values or ()) == len(candidates)
            and all(
                compare(atom(value), candidate["value"])
                for value, candidate in zip(values or (), candidates, strict=True)
            )
        )
    if kind == "IfcPropertyBoundedValue":
        if details.get("kind") != "bounded":
            return False
        return all(
            (atom(getattr(reference, name, None)) is None and details.get(key) is None)
            or (
                details.get(key) is not None
                and compare(atom(getattr(reference, name, None)), details[key]["value"])
            )
            for name, key in [
                ("LowerBoundValue", "lower"),
                ("UpperBoundValue", "upper"),
                ("SetPointValue", "set_point"),
            ]
        )
    if kind == "IfcPropertyTableValue":
        if details.get("kind") != "table" or details.get("expression") != reference.Expression:
            return False
        for name, key in [("DefiningUnit", "defining_unit_id"), ("DefinedUnit", "defined_unit_id")]:
            unit = getattr(reference, name, None)
            if details.get(key) != (unit.id() if unit else None):
                return False
        if details.get("interpolation") != getattr(reference, "CurveInterpolation", None):
            return False
        for name, key in [("DefiningValues", "defining"), ("DefinedValues", "defined")]:
            values, candidates = getattr(reference, name) or (), details.get(key, [])
            if len(values) != len(candidates) or not all(
                compare(atom(value), candidate["value"])
                for value, candidate in zip(values, candidates, strict=True)
            ):
                return False
        return True
    if kind == "IfcPropertyReferenceValue":
        target = reference.PropertyReference
        return (
            details.get("kind") == "reference"
            and target is not None
            and details.get("express_id") == target.id()
            and details.get("ifc_type") == target.is_a()
        )
    if kind == "IfcComplexProperty":
        if details.get("kind") != "complex" or details.get("usage_name") != reference.UsageName:
            return False
        children = {prop["name"]: prop for prop in details.get("properties", [])}
        expected = {prop.Name: prop for prop in reference.HasProperties or () if prop.Name}
        return children.keys() == expected.keys() and all(
            matches(prop, children[name], compare, path) for name, prop in expected.items()
        )
    return False


def unset(reference: object) -> bool:
    kind = reference.is_a()
    if kind == "IfcPropertySingleValue":
        return reference.NominalValue is None
    if kind == "IfcPropertyListValue":
        return reference.ListValues is None
    if kind == "IfcPropertyEnumeratedValue":
        return reference.EnumerationValues is None
    return False
