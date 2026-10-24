import json
import struct

import ifcopenshell
import pytest

import ifx_core


def box_model() -> tuple[bytes, int]:
    model = ifcopenshell.file(schema="IFC4")
    unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    units = model.create_entity("IfcUnitAssignment", Units=[unit])
    zero = model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0])
    axes = model.create_entity("IfcAxis2Placement3D", Location=zero)
    context = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Model",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=axes,
    )
    model.create_entity(
        "IfcProject",
        GlobalId=ifcopenshell.guid.new(),
        Name="Geometry test",
        UnitsInContext=units,
        RepresentationContexts=[context],
    )
    origin = model.create_entity("IfcCartesianPoint", Coordinates=[1e9, 2e9, 50000.0])
    placement = model.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=model.create_entity("IfcAxis2Placement3D", Location=origin),
    )
    profile = model.create_entity(
        "IfcRectangleProfileDef", ProfileType="AREA", XDim=2000.0, YDim=3000.0
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=axes,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=[0.0, 0.0, 1.0]),
        Depth=4000.0,
    )
    shape = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    product = model.create_entity("IfcProductDefinitionShape", Representations=[shape])
    slab = model.create_entity(
        "IfcSlab",
        GlobalId=ifcopenshell.guid.new(),
        Name="Box",
        ObjectPlacement=placement,
        Representation=product,
    )
    prop = model.create_entity(
        "IfcPropertySingleValue",
        Name="SourceLength",
        NominalValue=model.create_entity("IfcLengthMeasure", 2000.0),
    )
    pset = model.create_entity(
        "IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_Test", HasProperties=[prop]
    )
    slab_type = model.create_entity(
        "IfcSlabType",
        GlobalId=ifcopenshell.guid.new(),
        Name="Box type",
        HasPropertySets=[pset],
        PredefinedType="FLOOR",
    )
    model.create_entity(
        "IfcRelDefinesByType",
        GlobalId=ifcopenshell.guid.new(),
        RelatingType=slab_type,
        RelatedObjects=[slab],
    )
    return model.to_string().encode(), slab.id()


def test_geometry_world_metres_and_properties_source_units() -> None:
    source, element_id = box_model()
    result = ifx_core.extract_ifc(source, "high")
    geometry = result["geometry"]
    mesh = geometry["elements"][element_id]
    points = list(struct.iter_unpack("<ddd", mesh["vertices"]))
    lower = [min(point[axis] for point in points) for axis in range(3)]
    upper = [max(point[axis] for point in points) for axis in range(3)]
    assert lower == pytest.approx([999999, 1999998.5, 50])
    assert upper == pytest.approx([1000001, 2000001.5, 54])
    assert geometry["rtc_offset"] != [0, 0, 0]
    row = result["entities"]["entities"][element_id]
    assert row["placement"][12:15] == pytest.approx([1e6, 2e6, 50])
    assert row["property_sets"][0]["properties"][0]["value"] == "2000"
    assert result["entities"]["length_unit_scale"] == 0.001
    assert result["model"]["schema"] == "IFC4"
    assert json.loads(ifx_core.geometry_data_json(source, "high"))["elements"][str(element_id)][
        "vertices"
    ] == [list(point) for point in points]
    assert (
        ifx_core.entity_data(source, type_properties=False)["entities"][element_id]["property_sets"]
        == []
    )


def test_extraction_rejects_invalid_schema_and_quality() -> None:
    source, _ = box_model()
    with pytest.raises(RuntimeError, match="quality"):
        ifx_core.extract_ifc(source, "unknown")
    with pytest.raises(RuntimeError, match="schema"):
        ifx_core.extract_ifc(b"not an IFC file")
