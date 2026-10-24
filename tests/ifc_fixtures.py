from typing import Any

import ifcopenshell


def _guid() -> str:
    return ifcopenshell.guid.new()


def _root(model: Any, prefix: str | None) -> tuple[Any, Any]:
    length_unit = model.create_entity(
        "IfcSIUnit", UnitType="LENGTHUNIT", Prefix=prefix, Name="METRE"
    )
    units = model.create_entity("IfcUnitAssignment", Units=[length_unit])
    project = model.create_entity(
        "IfcProject", GlobalId=_guid(), Name="Test project", UnitsInContext=units
    )
    return project, length_unit


def _object(model: Any, ifc_class: str, name: str) -> Any:
    return model.create_entity(ifc_class, GlobalId=_guid(), Name=name)


def _rel(model: Any, ifc_class: str, **attributes: Any) -> Any:
    return model.create_entity(ifc_class, GlobalId=_guid(), **attributes)


def spatial_model(schema: str, prefix: str | None = "MILLI") -> tuple[Any, dict[str, Any]]:
    """Build a small schema-valid model covering every spatial relationship path."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, prefix)
    site = _object(model, "IfcSite", "Campus")
    building = _object(model, "IfcBuilding", "Headquarters")
    building.LongName = "Main building"
    storey = _object(model, "IfcBuildingStorey", "Level 01")
    storey.Elevation = 3000.0 if prefix == "MILLI" else 3.0
    placed_storey = _object(model, "IfcBuildingStorey", "Level 02")
    z = 6000.0 if prefix == "MILLI" else 6.0
    point = model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, z])
    axis = model.create_entity("IfcAxis2Placement3D", Location=point)
    placed_storey.ObjectPlacement = model.create_entity("IfcLocalPlacement", RelativePlacement=axis)
    space = _object(model, "IfcSpace", "Room 101")
    zone = _object(model, "IfcSpatialZone", "Fire zone")
    orphan = _object(model, "IfcSpace", "Unattached room")

    wall = _object(model, "IfcWall", "External wall")
    wall_part = _object(model, "IfcBuildingElementPart", "Aggregated leaf")
    nested_part = _object(model, "IfcBuildingElementPart", "Nested leaf")
    furniture = _object(model, "IfcFurniture", "Desk")
    zone_element = _object(model, "IfcFurnishingElement", "Zone equipment")
    wall_type = _object(model, "IfcWallType", "External wall type")

    _rel(model, "IfcRelAggregates", RelatingObject=project, RelatedObjects=[site])
    _rel(model, "IfcRelAggregates", RelatingObject=site, RelatedObjects=[building])
    _rel(
        model,
        "IfcRelAggregates",
        RelatingObject=building,
        RelatedObjects=[storey, placed_storey],
    )
    _rel(model, "IfcRelAggregates", RelatingObject=storey, RelatedObjects=[space, zone])
    _rel(model, "IfcRelAggregates", RelatingObject=wall, RelatedObjects=[wall_part])
    _rel(model, "IfcRelNests", RelatingObject=wall, RelatedObjects=[nested_part])
    _rel(
        model,
        "IfcRelContainedInSpatialStructure",
        RelatedElements=[wall],
        RelatingStructure=storey,
    )
    _rel(
        model,
        "IfcRelContainedInSpatialStructure",
        RelatedElements=[furniture],
        RelatingStructure=space,
    )
    _rel(
        model,
        "IfcRelContainedInSpatialStructure",
        RelatedElements=[zone_element],
        RelatingStructure=zone,
    )
    _rel(
        model,
        "IfcRelReferencedInSpatialStructure",
        RelatedElements=[furniture],
        RelatingStructure=storey,
    )
    _rel(model, "IfcRelDefinesByType", RelatedObjects=[wall], RelatingType=wall_type)

    handles = {
        "project": project,
        "site": site,
        "building": building,
        "storey": storey,
        "placed_storey": placed_storey,
        "space": space,
        "zone": zone,
        "orphan": orphan,
        "wall": wall,
        "wall_part": wall_part,
        "nested_part": nested_part,
        "furniture": furniture,
        "zone_element": zone_element,
    }

    if schema == "IFC4X3":
        facility_specs = [
            ("IfcFacility", ["IfcFacilityPart", "IfcFacilityPartCommon"]),
            ("IfcBridge", ["IfcBridgePart"]),
            ("IfcRoad", ["IfcRoadPart"]),
            ("IfcRailway", ["IfcRailwayPart"]),
            ("IfcMarineFacility", ["IfcMarinePart"]),
        ]
        for facility_class, part_classes in facility_specs:
            facility = _object(model, facility_class, f"Test {facility_class}")
            facility.CompositionType = "ELEMENT"
            parts = []
            for part_class in part_classes:
                part = _object(model, part_class, f"Test {part_class}")
                part.CompositionType = "ELEMENT"
                part.UsageType = "LONGITUDINAL"
                parts.append(part)
                handles[part_class] = part
            facility_element = _object(
                model, "IfcBuildingElementProxy", f"Element in {facility_class}"
            )
            _rel(model, "IfcRelAggregates", RelatingObject=project, RelatedObjects=[facility])
            _rel(model, "IfcRelAggregates", RelatingObject=facility, RelatedObjects=parts)
            _rel(
                model,
                "IfcRelContainedInSpatialStructure",
                RelatedElements=[facility_element],
                RelatingStructure=facility,
            )
            handles[facility_class] = facility
            handles[f"{facility_class}_element"] = facility_element

    return model, handles


def material_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build all currently supported material families and assignment paths."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    elements = [_object(model, "IfcWall", f"Wall {index}") for index in range(8)]
    wall_type = _object(model, "IfcWallType", "Typed wall")

    concrete = model.create_entity(
        "IfcMaterial", Name="Concrete", Description="Structural concrete", Category="Structure"
    )
    insulation = model.create_entity("IfcMaterial", Name="Insulation", Category="Thermal")
    steel = model.create_entity("IfcMaterial", Name="Steel", Category="Metal")

    layer_core = model.create_entity(
        "IfcMaterialLayer",
        Material=concrete,
        LayerThickness=200.0,
        IsVentilated=False,
        Name="Core",
        Description="Load-bearing layer",
        Category="Structure",
        Priority=100,
    )
    layer_finish = model.create_entity(
        "IfcMaterialLayer",
        Material=insulation,
        LayerThickness=50.0,
        IsVentilated=True,
        Name="Insulation",
        Category="Thermal",
        Priority=50,
    )
    layer_set = model.create_entity(
        "IfcMaterialLayerSet",
        MaterialLayers=[layer_core, layer_finish],
        LayerSetName="Wall build-up",
        Description="Two-layer wall",
    )
    layer_usage = model.create_entity(
        "IfcMaterialLayerSetUsage",
        ForLayerSet=layer_set,
        LayerSetDirection="AXIS2",
        DirectionSense="POSITIVE",
        OffsetFromReferenceLine=0.0,
    )

    rectangle = model.create_entity(
        "IfcRectangleProfileDef", ProfileType="AREA", ProfileName="RHS", XDim=200.0, YDim=100.0
    )
    material_profile = model.create_entity(
        "IfcMaterialProfile",
        Name="Steel profile",
        Description="Primary section",
        Material=steel,
        Profile=rectangle,
        Priority=80,
        Category="Structure",
    )
    profile_set = model.create_entity(
        "IfcMaterialProfileSet",
        Name="Beam set",
        Description="Structural profile",
        MaterialProfiles=[material_profile],
    )
    profile_usage = model.create_entity(
        "IfcMaterialProfileSetUsage", ForProfileSet=profile_set, CardinalPoint=5
    )

    core = model.create_entity(
        "IfcMaterialConstituent",
        Name="Core",
        Description="Concrete fraction",
        Material=concrete,
        Fraction=0.75,
        Category="Structure",
    )
    finish = model.create_entity(
        "IfcMaterialConstituent",
        Name="Finish",
        Material=insulation,
        Fraction=0.25,
        Category="Finish",
    )
    constituent_set = model.create_entity(
        "IfcMaterialConstituentSet",
        Name="Composite",
        Description="Core and finish",
        MaterialConstituents=[core, finish],
    )
    material_list = model.create_entity("IfcMaterialList", Materials=[concrete, steel])

    definitions = [
        concrete,
        layer_set,
        layer_usage,
        profile_set,
        profile_usage,
        constituent_set,
        material_list,
    ]
    for element, definition in zip(elements[:7], definitions, strict=True):
        _rel(
            model,
            "IfcRelAssociatesMaterial",
            RelatedObjects=[element],
            RelatingMaterial=definition,
        )

    _rel(
        model,
        "IfcRelAssociatesMaterial",
        RelatedObjects=[wall_type],
        RelatingMaterial=insulation,
    )
    _rel(
        model,
        "IfcRelDefinesByType",
        RelatedObjects=[elements[7]],
        RelatingType=wall_type,
    )

    # Multiple direct associations are legal in real-world files. The core
    # preserves all unique definitions in relationship-ID order.
    multiple = _object(model, "IfcWall", "Multiple materials")
    _rel(
        model,
        "IfcRelAssociatesMaterial",
        RelatedObjects=[multiple],
        RelatingMaterial=steel,
    )
    _rel(
        model,
        "IfcRelAssociatesMaterial",
        RelatedObjects=[multiple],
        RelatingMaterial=concrete,
    )
    _rel(
        model,
        "IfcRelAssociatesMaterial",
        RelatedObjects=[multiple],
        RelatingMaterial=steel,
    )

    return model, {
        "project": project,
        "elements": elements,
        "wall_type": wall_type,
        "multiple": multiple,
        "concrete": concrete,
        "insulation": insulation,
        "steel": steel,
        "layer_set": layer_set,
        "layer_usage": layer_usage,
        "profile_set": profile_set,
        "profile_usage": profile_usage,
        "constituent_set": constituent_set,
        "material_list": material_list,
    }


def opening_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build two host/opening/filling chains inside a spatial hierarchy."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    site = _object(model, "IfcSite", "Site")
    building = _object(model, "IfcBuilding", "Building")
    storey = _object(model, "IfcBuildingStorey", "Level 01")
    wall = _object(model, "IfcWall", "Wall with openings")
    door_opening = _object(model, "IfcOpeningElement", "Door opening")
    window_opening = _object(model, "IfcOpeningElement", "Window opening")
    door = _object(model, "IfcDoor", "Door")
    window = _object(model, "IfcWindow", "Window")

    _rel(model, "IfcRelAggregates", RelatingObject=project, RelatedObjects=[site])
    _rel(model, "IfcRelAggregates", RelatingObject=site, RelatedObjects=[building])
    _rel(model, "IfcRelAggregates", RelatingObject=building, RelatedObjects=[storey])
    _rel(
        model,
        "IfcRelContainedInSpatialStructure",
        RelatedElements=[wall],
        RelatingStructure=storey,
    )
    door_void = _rel(
        model,
        "IfcRelVoidsElement",
        RelatingBuildingElement=wall,
        RelatedOpeningElement=door_opening,
    )
    door_fill = _rel(
        model,
        "IfcRelFillsElement",
        RelatingOpeningElement=door_opening,
        RelatedBuildingElement=door,
    )
    window_void = _rel(
        model,
        "IfcRelVoidsElement",
        RelatingBuildingElement=wall,
        RelatedOpeningElement=window_opening,
    )
    window_fill = _rel(
        model,
        "IfcRelFillsElement",
        RelatingOpeningElement=window_opening,
        RelatedBuildingElement=window,
    )

    return model, {
        "project": project,
        "site": site,
        "building": building,
        "storey": storey,
        "wall": wall,
        "door_opening": door_opening,
        "window_opening": window_opening,
        "door": door,
        "window": window,
        "door_void": door_void,
        "door_fill": door_fill,
        "window_void": window_void,
        "window_fill": window_fill,
    }


def unit_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build representative SI, conversion, derived, and monetary project units."""

    model = ifcopenshell.file(schema=schema)
    dimensions = model.create_entity("IfcDimensionalExponents", 0, 0, 0, 0, 0, 0, 0)
    length = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    area = model.create_entity(
        "IfcSIUnit", UnitType="AREAUNIT", Prefix="MILLI", Name="SQUARE_METRE"
    )
    radians = model.create_entity("IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN")
    angle_factor = model.create_entity(
        "IfcMeasureWithUnit",
        ValueComponent=model.createIfcPlaneAngleMeasure(0.0174532925199433),
        UnitComponent=radians,
    )
    degrees = model.create_entity(
        "IfcConversionBasedUnit",
        Dimensions=dimensions,
        UnitType="PLANEANGLEUNIT",
        Name="DEGREE",
        ConversionFactor=angle_factor,
    )
    volume = model.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
    seconds = model.create_entity("IfcSIUnit", UnitType="TIMEUNIT", Name="SECOND")
    volume_element = model.create_entity("IfcDerivedUnitElement", Unit=volume, Exponent=1)
    time_element = model.create_entity("IfcDerivedUnitElement", Unit=seconds, Exponent=-1)
    flow = model.create_entity(
        "IfcDerivedUnit",
        Elements=[volume_element, time_element],
        UnitType="VOLUMETRICFLOWRATEUNIT",
    )
    money = model.create_entity("IfcMonetaryUnit", Currency="USD")
    assignment = model.create_entity(
        "IfcUnitAssignment", Units=[length, area, degrees, flow, money]
    )
    project = model.create_entity(
        "IfcProject", GlobalId=_guid(), Name="Unit project", UnitsInContext=assignment
    )
    return model, {
        "project": project,
        "assignment": assignment,
        "length": length,
        "area": area,
        "degrees": degrees,
        "flow": flow,
        "money": money,
    }


def classification_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build nested, direct, system-level, and type-inherited classifications."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    wall = _object(model, "IfcWall", "Classified wall")
    system_wall = _object(model, "IfcWall", "System-classified wall")
    wall_type = _object(model, "IfcWallType", "Classified wall type")

    system_kwargs = {
        "Source": "NBS",
        "Edition": "2025",
        "EditionDate": "2025-01-01",
        "Name": "Uniclass 2015",
        "Description": "Test classification system",
        "ReferenceTokens": ["Pr"],
    }
    system_kwargs["Location" if schema == "IFC4" else "Specification"] = (
        "https://example.test/uniclass"
    )
    system = model.create_entity("IfcClassification", **system_kwargs)
    parent = model.create_entity(
        "IfcClassificationReference",
        Location="https://example.test/uniclass/Pr_20",
        Identification="Pr_20",
        Name="Structural and general products",
        ReferencedSource=system,
        Description="Parent classification",
        Sort="20",
    )
    child = model.create_entity(
        "IfcClassificationReference",
        Location="https://example.test/uniclass/Pr_20_93",
        Identification="Pr_20_93",
        Name="Unit structure and general products",
        ReferencedSource=parent,
        Description="Child classification",
        Sort="93",
    )

    type_relationship = _rel(
        model, "IfcRelDefinesByType", RelatedObjects=[wall], RelatingType=wall_type
    )
    direct_relationship = _rel(
        model,
        "IfcRelAssociatesClassification",
        RelatedObjects=[wall],
        RelatingClassification=child,
    )
    inherited_relationship = _rel(
        model,
        "IfcRelAssociatesClassification",
        RelatedObjects=[wall_type],
        RelatingClassification=parent,
    )
    duplicate_relationship = _rel(
        model,
        "IfcRelAssociatesClassification",
        RelatedObjects=[wall_type],
        RelatingClassification=child,
    )
    system_relationship = _rel(
        model,
        "IfcRelAssociatesClassification",
        RelatedObjects=[system_wall],
        RelatingClassification=system,
    )

    return model, {
        "project": project,
        "wall": wall,
        "system_wall": system_wall,
        "wall_type": wall_type,
        "system": system,
        "parent": parent,
        "child": child,
        "type_relationship": type_relationship,
        "direct_relationship": direct_relationship,
        "inherited_relationship": inherited_relationship,
        "duplicate_relationship": duplicate_relationship,
        "system_relationship": system_relationship,
    }


def document_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build direct and type-inherited document assignments with reference merging."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    wall = _object(model, "IfcWall", "Documented wall")
    wall_type = _object(model, "IfcWallType", "Documented wall type")
    information = model.create_entity(
        "IfcDocumentInformation",
        Identification="DOC-001",
        Name="Installation manual",
        Description="Canonical document description",
        Location="https://example.test/manual.pdf",
        Purpose="Installation",
        IntendedUse="Construction",
        Scope="Project",
        Revision="B",
        ElectronicFormat="application/pdf",
        ValidFrom="2025-01-01",
        ValidUntil="2030-01-01",
        Confidentiality="PUBLIC",
        Status="FINAL",
    )
    reference = model.create_entity(
        "IfcDocumentReference",
        Location="manual.pdf",
        Description="Reference-specific description",
        ReferencedDocument=information,
    )
    type_relationship = _rel(
        model, "IfcRelDefinesByType", RelatedObjects=[wall], RelatingType=wall_type
    )
    direct_relationship = _rel(
        model,
        "IfcRelAssociatesDocument",
        RelatedObjects=[wall],
        RelatingDocument=reference,
    )
    inherited_relationship = _rel(
        model,
        "IfcRelAssociatesDocument",
        RelatedObjects=[wall_type],
        RelatingDocument=information,
    )
    duplicate_relationship = _rel(
        model,
        "IfcRelAssociatesDocument",
        RelatedObjects=[wall_type],
        RelatingDocument=reference,
    )
    return model, {
        "project": project,
        "wall": wall,
        "wall_type": wall_type,
        "information": information,
        "reference": reference,
        "type_relationship": type_relationship,
        "direct_relationship": direct_relationship,
        "inherited_relationship": inherited_relationship,
        "duplicate_relationship": duplicate_relationship,
    }


def group_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build group, zone, system, factored, and product assignments."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    wall = _object(model, "IfcWall", "Assigned wall")
    space = _object(model, "IfcSpace", "Assigned space")
    group = _object(model, "IfcGroup", "Inspection group")
    group.ObjectType = "Review set"
    zone = _object(model, "IfcZone", "Fire zone")
    zone.LongName = "Fire compartment A"
    system = _object(model, "IfcSystem", "Building service")
    distribution_system = _object(model, "IfcDistributionSystem", "Supply air")
    distribution_system.LongName = "Supply air system"
    distribution_system.PredefinedType = "VENTILATION"

    group_relationship = _rel(
        model,
        "IfcRelAssignsToGroup",
        RelatedObjects=[wall, space],
        RelatingGroup=group,
    )
    zone_relationship = _rel(
        model, "IfcRelAssignsToGroup", RelatedObjects=[space], RelatingGroup=zone
    )
    factor_relationship = _rel(
        model,
        "IfcRelAssignsToGroupByFactor",
        RelatedObjects=[wall],
        RelatingGroup=system,
        Factor=0.25,
    )
    distribution_relationship = _rel(
        model,
        "IfcRelAssignsToGroup",
        RelatedObjects=[wall],
        RelatingGroup=distribution_system,
    )
    product_relationship = _rel(
        model,
        "IfcRelAssignsToProduct",
        RelatedObjects=[space],
        RelatingProduct=wall,
    )
    return model, {
        "project": project,
        "wall": wall,
        "space": space,
        "group": group,
        "zone": zone,
        "system": system,
        "distribution_system": distribution_system,
        "group_relationship": group_relationship,
        "zone_relationship": zone_relationship,
        "factor_relationship": factor_relationship,
        "distribution_relationship": distribution_relationship,
        "product_relationship": product_relationship,
    }


def connection_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build element/path, port, and all space-boundary relationship levels."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    wall_a = _object(model, "IfcWall", "Connected wall A")
    wall_b = _object(model, "IfcWall", "Connected wall B")
    space = _object(model, "IfcSpace", "Bounded space")
    segment_a = _object(model, "IfcPipeSegment", "Pipe A")
    segment_b = _object(model, "IfcPipeSegment", "Pipe B")
    port_a = _object(model, "IfcDistributionPort", "Pipe A outlet")
    port_a.FlowDirection = "SOURCE"
    port_a.PredefinedType = "PIPE"
    port_a.SystemType = "DOMESTICCOLDWATER"
    port_b = _object(model, "IfcDistributionPort", "Pipe B inlet")
    port_b.FlowDirection = "SINK"
    port_b.PredefinedType = "PIPE"
    port_b.SystemType = "DOMESTICCOLDWATER"

    element_relationship = _rel(
        model,
        "IfcRelConnectsElements",
        Name="Generic connection",
        RelatingElement=wall_a,
        RelatedElement=wall_b,
    )
    path_relationship = _rel(
        model,
        "IfcRelConnectsPathElements",
        Name="Path connection",
        RelatingElement=wall_a,
        RelatedElement=wall_b,
        RelatingPriorities=[10, 20],
        RelatedPriorities=[30],
        RelatingConnectionType="ATSTART",
        RelatedConnectionType="ATEND",
    )
    port_a_relationship = _rel(
        model,
        "IfcRelConnectsPortToElement",
        RelatingPort=port_a,
        RelatedElement=segment_a,
    )
    port_b_relationship = _rel(
        model,
        "IfcRelConnectsPortToElement",
        RelatingPort=port_b,
        RelatedElement=segment_b,
    )
    ports_relationship = _rel(
        model,
        "IfcRelConnectsPorts",
        RelatingPort=port_a,
        RelatedPort=port_b,
        RealizingElement=segment_a,
    )
    boundary = _rel(
        model,
        "IfcRelSpaceBoundary",
        RelatingSpace=space,
        RelatedBuildingElement=wall_a,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="INTERNAL",
    )
    boundary_first = _rel(
        model,
        "IfcRelSpaceBoundary1stLevel",
        RelatingSpace=space,
        RelatedBuildingElement=wall_b,
        PhysicalOrVirtualBoundary="PHYSICAL",
        InternalOrExternalBoundary="EXTERNAL",
    )
    boundary_second = _rel(
        model,
        "IfcRelSpaceBoundary2ndLevel",
        RelatingSpace=space,
        RelatedBuildingElement=wall_b,
        PhysicalOrVirtualBoundary="VIRTUAL",
        InternalOrExternalBoundary="INTERNAL",
        ParentBoundary=boundary_first,
    )
    return model, {
        "project": project,
        "wall_a": wall_a,
        "wall_b": wall_b,
        "space": space,
        "segment_a": segment_a,
        "segment_b": segment_b,
        "port_a": port_a,
        "port_b": port_b,
        "element_relationship": element_relationship,
        "path_relationship": path_relationship,
        "port_a_relationship": port_a_relationship,
        "port_b_relationship": port_b_relationship,
        "ports_relationship": ports_relationship,
        "boundary": boundary,
        "boundary_first": boundary_first,
        "boundary_second": boundary_second,
    }


def georeference_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build an explicit map conversion and projected CRS."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    point = model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0])
    axis = model.create_entity("IfcAxis2Placement3D", Location=point)
    context = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Model",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=axis,
    )
    project.RepresentationContexts = [context]
    map_unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    crs = model.create_entity(
        "IfcProjectedCRS",
        Name="EPSG:28992",
        Description="Amersfoort / RD New",
        GeodeticDatum="Amersfoort",
        VerticalDatum="NAP",
        MapProjection="Oblique Stereographic",
        MapZone="Netherlands",
        MapUnit=map_unit,
    )
    conversion = model.create_entity(
        "IfcMapConversion",
        SourceCRS=context,
        TargetCRS=crs,
        Eastings=155000.0,
        Northings=463000.0,
        OrthogonalHeight=1.5,
        XAxisAbscissa=0.0,
        XAxisOrdinate=1.0,
        Scale=0.9999,
    )
    return model, {
        "project": project,
        "context": context,
        "map_unit": map_unit,
        "crs": crs,
        "conversion": conversion,
    }


def site_georeference_model(schema: str = "IFC4") -> tuple[Any, dict[str, Any]]:
    """Build the legacy IfcSite latitude/longitude fallback supported by IFC Lite."""

    model = ifcopenshell.file(schema=schema)
    project, _ = _root(model, "MILLI")
    site = _object(model, "IfcSite", "Bogotá site")
    site.RefLatitude = (4, 36, 0, 0)
    site.RefLongitude = (-74, 5, 0, 0)
    site.RefElevation = 2600.0
    _rel(model, "IfcRelAggregates", RelatingObject=project, RelatedObjects=[site])
    return model, {"project": project, "site": site}


def as_bytes(model: Any) -> bytes:
    return model.to_string().encode("utf-8")
