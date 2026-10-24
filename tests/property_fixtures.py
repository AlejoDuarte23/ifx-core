import ifcopenshell

from scripts.ifc_validation.fixtures import make_fixture


def make_property_fixture(schema: str) -> tuple[bytes, dict[str, int]]:
    source, _ = make_fixture(schema, "metres")
    model = ifcopenshell.file.from_string(source.decode())
    pset = model.by_type("IfcPropertySet")[0]
    typed = model.create_entity
    unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE", Prefix="MILLI")
    enumeration = typed(
        "IfcPropertyEnumeration",
        Name="Shapes",
        EnumerationValues=[typed("IfcLabel", "ROUND"), typed("IfcLabel", "SQUARE")],
    )
    items = [
        typed(
            "IfcPropertySingleValue",
            Name="Wrapped identifier",
            NominalValue=typed("IfcIdentifier", "line break"),
        ),
        typed(
            "IfcPropertyEnumeratedValue",
            Name="Shape",
            EnumerationValues=[typed("IfcLabel", "ROUND")],
            EnumerationReference=enumeration,
        ),
        typed(
            "IfcPropertyListValue",
            Name="Lengths",
            ListValues=[typed("IfcLengthMeasure", 200.0), typed("IfcLengthMeasure", 450.0)],
            Unit=unit,
        ),
        typed(
            "IfcPropertyBoundedValue",
            Name="Range",
            LowerBoundValue=typed("IfcLengthMeasure", 100.0),
            UpperBoundValue=typed("IfcLengthMeasure", 500.0),
            Unit=unit,
        ),
        typed(
            "IfcPropertyTableValue",
            Name="Curve",
            DefiningValues=[typed("IfcReal", 1.0), typed("IfcReal", 2.0)],
            DefinedValues=[typed("IfcReal", 10.0), typed("IfcReal", 40.0)],
            Expression="y=x*x*10",
        ),
        typed(
            "IfcPropertyReferenceValue",
            Name="Material reference",
            PropertyReference=model.by_type("IfcMaterial")[0],
        ),
    ]
    if schema != "IFC2X3":
        items[3].SetPointValue = typed("IfcLengthMeasure", 300.0)
    child = typed(
        "IfcPropertySingleValue", Name="Height", NominalValue=typed("IfcLengthMeasure", 4.0)
    )
    nested = typed(
        "IfcComplexProperty",
        Name="Dimensions",
        UsageName="Geometry",
        HasProperties=[child, items[2]],
    )
    items.append(nested)
    pset.HasProperties = [*pset.HasProperties, *items]
    material = model.by_type("IfcMaterial")[0]
    stiffness = typed(
        "IfcPropertySingleValue",
        Name="YoungModulus",
        NominalValue=typed("IfcPressureMeasure", 210000.0),
    )
    if schema == "IFC2X3":
        material_set = typed(
            "IfcExtendedMaterialProperties",
            Material=material,
            Name="Material stiffness",
            ExtendedProperties=[stiffness, items[1]],
        )
        profile = model.by_type("IfcRectangleProfileDef")[0]
        profile_set = typed(
            "IfcGeneralProfileProperties",
            ProfileName="Cross section",
            ProfileDefinition=profile,
            CrossSectionArea=6.0,
        )
    else:
        material_set = typed(
            "IfcMaterialProperties",
            Material=material,
            Name="Material stiffness",
            Properties=[stiffness, items[1]],
        )
        profile = model.by_type("IfcRectangleProfileDef")[0]
        profile_set = typed(
            "IfcProfileProperties",
            ProfileDefinition=profile,
            Name="Cross section",
            Properties=[
                typed(
                    "IfcPropertySingleValue",
                    Name="CrossSectionArea",
                    NominalValue=typed("IfcAreaMeasure", 6.0),
                )
            ],
        )
    return model.to_string().replace(
        "IFCIDENTIFIER('line break')", "IFCIDENTIFIER\r\n('line break')"
    ).encode(), {
        "wall": model.by_type("IfcWall")[0].id(),
        "material": material.id(),
        "material_set": material_set.id(),
        "profile": profile.id(),
        "profile_set": profile_set.id(),
        "unit": unit.id(),
        "complex": nested.id(),
        "pset": pset.id(),
    }
