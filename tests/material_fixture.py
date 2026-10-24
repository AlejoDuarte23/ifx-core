import ifcopenshell


def material_window(schema: str) -> tuple[bytes, int]:
    model = ifcopenshell.file(schema=schema)
    point = model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0])
    axes = model.create_entity("IfcAxis2Placement3D", Location=point)
    context = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=axes,
    )
    unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    model.create_entity(
        "IfcProject",
        GlobalId=ifcopenshell.guid.new(),
        Name="Material window",
        RepresentationContexts=[context],
        UnitsInContext=model.create_entity("IfcUnitAssignment", Units=[unit]),
    )
    solids = []
    for x, width, color, transparency in [
        (0.0, 0.12, [0.9, 0.9, 0.9], 0.0),
        (0.88, 0.12, [0.7, 0.3, 0.24], 0.0),
        (0.12, 0.76, [0.1, 0.1, 0.1], 0.88),
    ]:
        position = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity(
                "IfcCartesianPoint", Coordinates=[x + width / 2, 0.0, 0.0]
            ),
        )
        profile = model.create_entity(
            "IfcRectangleProfileDef", ProfileType="AREA", XDim=width, YDim=0.06
        )
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=position,
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=[0.0, 0.0, 1.0]),
            Depth=1.0,
        )
        rgb = model.create_entity("IfcColourRgb", Red=color[0], Green=color[1], Blue=color[2])
        rendering = model.create_entity(
            "IfcSurfaceStyleRendering",
            SurfaceColour=rgb,
            Transparency=transparency,
            ReflectanceMethod="NOTDEFINED",
        )
        style = model.create_entity("IfcSurfaceStyle", Side="BOTH", Styles=[rendering])
        styles = (
            [model.create_entity("IfcPresentationStyleAssignment", Styles=[style])]
            if schema == "IFC2X3"
            else [style]
        )
        model.create_entity("IfcStyledItem", Item=solid, Styles=styles)
        solids.append(solid)
    shape = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=solids,
    )
    window = model.create_entity(
        "IfcWindow",
        GlobalId=ifcopenshell.guid.new(),
        Name="Frame and glass",
        Representation=model.create_entity("IfcProductDefinitionShape", Representations=[shape]),
        ObjectPlacement=model.create_entity("IfcLocalPlacement", RelativePlacement=axes),
    )
    return model.to_string().encode(), window.id()
