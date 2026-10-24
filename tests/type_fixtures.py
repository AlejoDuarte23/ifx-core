import uuid

import ifcopenshell

from scripts.ifc_validation.fixtures import NAMESPACE, make_fixture


def make_type_fixture(schema: str) -> tuple[bytes, dict[str, int]]:
    source, _ = make_fixture(schema, "metres")
    model = ifcopenshell.file.from_string(source.decode())
    project = model.by_type("IfcProject")[0]
    wall = model.by_type("IfcWall")[0]

    def guid(name: str) -> str:
        return ifcopenshell.guid.compress(uuid.uuid5(NAMESPACE, f"{schema}-{name}").hex)

    duct = model.create_entity(
        "IfcFlowSegment" if schema == "IFC2X3" else "IfcDuctSegment",
        GlobalId=guid("linked-duct"),
        OwnerHistory=project.OwnerHistory,
        ObjectPlacement=wall.ObjectPlacement,
        Representation=wall.Representation,
    )
    for relationship in model.by_type("IfcRelDefinesByProperties"):
        relationship.RelatedObjects = [
            duct if item == wall else item for item in relationship.RelatedObjects
        ]
    model.remove(wall)
    prop = model.create_entity(
        "IfcPropertySingleValue",
        Name="TypeCode",
        NominalValue=model.create_entity("IfcIdentifier", "HVAC-1000"),
    )
    pset = model.create_entity(
        "IfcPropertySet",
        GlobalId=guid("linked-type-pset"),
        OwnerHistory=project.OwnerHistory,
        Name="Pset_Validation",
        HasProperties=[prop],
    )
    linked_type = model.create_entity(
        "IfcDuctSegmentType",
        GlobalId=guid("linked-duct-type"),
        OwnerHistory=project.OwnerHistory,
        Name="SS1002",
        Description="Rectangular duct",
        ApplicableOccurrence="Ventilation ducts",
        HasPropertySets=[pset],
        Tag="TYPE-01",
        ElementType="HVAC-DUCT-1000x500",
        PredefinedType="RIGIDSEGMENT",
    )
    relation = model.create_entity(
        "IfcRelDefinesByType",
        GlobalId=guid("linked-type-assignment"),
        OwnerHistory=project.OwnerHistory,
        RelatedObjects=[duct],
        RelatingType=linked_type,
    )
    return model.to_string().encode(), {
        "duct": duct.id(),
        "type": linked_type.id(),
        "relation": relation.id(),
    }
