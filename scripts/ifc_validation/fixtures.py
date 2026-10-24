import uuid

import ifcopenshell

SCHEMAS = ("IFC2X3", "IFC4", "IFC4X3_ADD2")
FEATURES = (
    "metres",
    "millimetres",
    "feet",
    "nested-rotation",
    "large-coordinates",
    "mapped-nonuniform",
    "opening",
    "door-type",
    "grid-placement",
    "quoted-header",
)
NAMESPACE = uuid.UUID("c0c65f4d-1d03-42dd-82f7-e134ac9b29ef")


def make_fixture(schema: str, feature: str) -> tuple[bytes, dict[str, object]]:
    if schema not in SCHEMAS or feature not in FEATURES:
        raise ValueError("unknown fixture schema or feature")
    model = ifcopenshell.file(schema=schema)
    case_id = f"{schema.lower()}-{feature}"
    owner = None
    if schema == "IFC2X3":
        person = model.create_entity("IfcPerson", FamilyName="Validation")
        organisation = model.create_entity("IfcOrganization", Name="IFX validation")
        user = model.create_entity(
            "IfcPersonAndOrganization", ThePerson=person, TheOrganization=organisation
        )
        app = model.create_entity(
            "IfcApplication",
            ApplicationDeveloper=organisation,
            Version="1",
            ApplicationFullName="IFX compatibility fixtures",
            ApplicationIdentifier="IFX",
        )
        owner = model.create_entity(
            "IfcOwnerHistory",
            OwningUser=user,
            OwningApplication=app,
            ChangeAction="ADDED",
            CreationDate=0,
        )

    def root(ifc_class: str, name: str, **attributes: object) -> object:
        return model.create_entity(
            ifc_class,
            GlobalId=ifcopenshell.guid.compress(uuid.uuid5(NAMESPACE, f"{case_id}-{name}").hex),
            OwnerHistory=owner,
            Name=name,
            **attributes,
        )

    scale = {"millimetres": 0.001, "feet": 0.3048}.get(feature, 1.0)

    def point(xyz: list[float]) -> object:
        return model.create_entity("IfcCartesianPoint", Coordinates=[float(v / scale) for v in xyz])

    def axes(xyz: list[float], direction: list[float] | None = None) -> object:
        return model.create_entity(
            "IfcAxis2Placement3D",
            Location=point(xyz),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=direction)
            if direction
            else None,
        )

    def placement(xyz: list[float], parent: object = None, rotation: bool = False) -> object:
        return model.create_entity(
            "IfcLocalPlacement",
            PlacementRelTo=parent,
            RelativePlacement=axes(xyz, [0.0, 1.0, 0.0] if rotation else None),
        )

    metre = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    if feature == "feet":
        dimensions = model.create_entity(
            "IfcDimensionalExponents",
            LengthExponent=1,
            MassExponent=0,
            TimeExponent=0,
            ElectricCurrentExponent=0,
            ThermodynamicTemperatureExponent=0,
            AmountOfSubstanceExponent=0,
            LuminousIntensityExponent=0,
        )
        unit = model.create_entity(
            "IfcConversionBasedUnit",
            Dimensions=dimensions,
            UnitType="LENGTHUNIT",
            Name="FOOT",
            ConversionFactor=model.create_entity(
                "IfcMeasureWithUnit",
                ValueComponent=model.create_entity("IfcLengthMeasure", scale),
                UnitComponent=metre,
            ),
        )
    elif feature == "millimetres":
        unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    else:
        unit = metre
    context = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Model",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-6 / scale,
        WorldCoordinateSystem=axes([0.0, 0.0, 0.0]),
    )
    root(
        "IfcProject",
        "Project",
        UnitsInContext=model.create_entity("IfcUnitAssignment", Units=[unit]),
        RepresentationContexts=[context],
    )

    def shape(width: float, length: float, height: float) -> object:
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=model.create_entity(
                "IfcRectangleProfileDef",
                ProfileType="AREA",
                XDim=width / scale,
                YDim=length / scale,
                Position=model.create_entity(
                    "IfcAxis2Placement2D",
                    Location=model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0]),
                ),
            ),
            Position=axes([0.0, 0.0, 0.0]),
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=[0.0, 0.0, 1.0]),
            Depth=height / scale,
        )
        return model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

    origin = [10.0, 20.0, 30.0]
    product_placement = placement(origin)
    lower, upper = [9.0, 18.5, 30.0], [11.0, 21.5, 34.0]
    area, volume = 52.0, 24.0
    if feature == "nested-rotation":
        product_placement = placement([2.0, 1.0, 4.0], placement([12.0, -7.0, 3.0], rotation=True))
        lower, upper = [9.5, -6.0, 7.0], [12.5, -4.0, 11.0]
    elif feature == "large-coordinates":
        origin = [1e6, 2e6, 50.0]
        product_placement = placement(origin)
        lower, upper = [999999.0, 1999998.5, 50.0], [1000001.0, 2000001.5, 54.0]
    elif feature == "grid-placement":
        grid_axes = []
        for tag, start, end in (
            ("U1", [-10.0, 0.0, 0.0], [10.0, 0.0, 0.0]),
            ("V1", [0.0, -10.0, 0.0], [0.0, 10.0, 0.0]),
        ):
            grid_axes.append(
                model.create_entity(
                    "IfcGridAxis",
                    AxisTag=tag,
                    SameSense=True,
                    AxisCurve=model.create_entity(
                        "IfcPolyline",
                        Points=[
                            model.create_entity("IfcCartesianPoint", Coordinates=start[:2]),
                            model.create_entity("IfcCartesianPoint", Coordinates=end[:2]),
                        ],
                    ),
                )
            )
        root(
            "IfcGrid",
            "Grid",
            ObjectPlacement=product_placement,
            UAxes=[grid_axes[0]],
            VAxes=[grid_axes[1]],
        )
        intersection = model.create_entity(
            "IfcVirtualGridIntersection",
            IntersectingAxes=grid_axes,
            OffsetDistances=[0.0, 0.0, 3.0],
        )
        grid_parent = product_placement
        product_placement = model.create_entity("IfcGridPlacement", PlacementLocation=intersection)
        if schema == "IFC4X3_ADD2":
            product_placement.PlacementRelTo = grid_parent
        lower, upper = [9.0, 18.5, 33.0], [11.0, 21.5, 37.0]

    body = shape(2.0, 3.0, 4.0)
    if feature == "mapped-nonuniform":
        mapping = model.create_entity(
            "IfcRepresentationMap",
            MappingOrigin=axes([0.0, 0.0, 0.0]),
            MappedRepresentation=body,
        )
        mapped = model.create_entity(
            "IfcMappedItem",
            MappingSource=mapping,
            MappingTarget=model.create_entity(
                "IfcCartesianTransformationOperator3DnonUniform",
                LocalOrigin=point([0.0, 0.0, 0.0]),
                Scale=2.0,
                Scale2=3.0,
                Scale3=0.5,
            ),
        )
        body = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="Body",
            RepresentationType="MappedRepresentation",
            Items=[mapped],
        )
        lower, upper, area, volume = [8.0, 15.5, 30.0], [12.0, 24.5, 32.0], 124.0, 72.0

    product = root(
        "IfcDoor" if feature == "door-type" else "IfcWall",
        "Element",
        ObjectPlacement=product_placement,
        Representation=model.create_entity("IfcProductDefinitionShape", Representations=[body]),
    )
    if feature == "door-type":
        product.OverallHeight = 4.0 / scale
        product.OverallWidth = 2.0 / scale
        if schema == "IFC4X3_ADD2":
            element_type = root(
                "IfcDoorType",
                "Door type",
                PredefinedType="DOOR",
                OperationType="SINGLE_SWING_LEFT",
                ParameterTakesPrecedence=False,
            )
        else:
            element_type = root(
                "IfcDoorStyle",
                "Door type",
                OperationType="SINGLE_SWING_LEFT",
                ConstructionType="ALUMINIUM",
                ParameterTakesPrecedence=False,
                Sizeable=True,
            )
        inherited = root(
            "IfcPropertySet",
            "Pset_TypeValidation",
            HasProperties=[
                model.create_entity(
                    "IfcPropertySingleValue",
                    Name="TypeValue",
                    NominalValue=model.create_entity("IfcLabel", "inherited"),
                )
            ],
        )
        element_type.HasPropertySets = [inherited]
        root(
            "IfcRelDefinesByType",
            "Type assignment",
            RelatedObjects=[product],
            RelatingType=element_type,
        )
    if feature == "opening":
        opening = root(
            "IfcOpeningElement",
            "Opening",
            ObjectPlacement=placement([0.0, 0.0, 0.0], product_placement),
            Representation=model.create_entity(
                "IfcProductDefinitionShape", Representations=[shape(1.0, 1.0, 4.0)]
            ),
        )
        root(
            "IfcRelVoidsElement",
            "Void",
            RelatingBuildingElement=product,
            RelatedOpeningElement=opening,
        )
        area, volume = 66.0, 20.0
    property_set = root(
        "IfcPropertySet",
        "Pset_Validation",
        HasProperties=[
            model.create_entity(
                "IfcPropertySingleValue",
                Name="SourceLength",
                NominalValue=model.create_entity("IfcLengthMeasure", 2.0 / scale),
            )
        ],
    )
    root(
        "IfcRelDefinesByProperties",
        "Properties",
        RelatedObjects=[product],
        RelatingPropertyDefinition=property_set,
    )
    material = model.create_entity("IfcMaterial", Name="Validation material")
    root(
        "IfcRelAssociatesMaterial", "Material", RelatedObjects=[product], RelatingMaterial=material
    )
    if feature == "quoted-header":
        model.header.file_description.description = (
            "FILE_SCHEMA(('IFC4X3_FAKE')); ENDSEC; 'quoted'",
        )
    model.header.file_name.time_stamp = "2026-01-01T00:00:00"
    return model.to_string().encode(), {
        "element_id": product.id(),
        "lower": lower,
        "upper": upper,
        "area_m2": area,
        "volume_m3": volume,
        "closed": True,
        "length_unit_scale": scale,
        "reference_method": "analytic"
        if feature == "grid-placement"
        else "ifcopenshell-and-analytic",
    }
