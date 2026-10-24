import ifcopenshell
import numpy as np
import pytest

import ifx_core
from scripts.ifc_validation.fixtures import make_fixture
from scripts.ifc_validation.mesh import mesh_metrics


def make_surface_fixture(schema: str, tilted: bool) -> tuple[bytes, int]:
    source, _ = make_fixture(schema, "metres")
    model = ifcopenshell.file.from_string(source.decode())
    curve = model.create_entity(
        "IfcPolyline",
        Points=[
            model.create_entity("IfcCartesianPoint", Coordinates=[-1.0, 0.0]),
            model.create_entity("IfcCartesianPoint", Coordinates=[1.0, 0.0]),
        ],
    )
    profile = model.create_entity("IfcArbitraryOpenProfileDef", ProfileType="CURVE", Curve=curve)
    axis = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=[0.0, 0.0, 0.0]),
        Axis=model.create_entity(
            "IfcDirection", DirectionRatios=[0.0, 1.0, 0.0] if tilted else [0.0, 0.0, 1.0]
        ),
        RefDirection=model.create_entity("IfcDirection", DirectionRatios=[1.0, 0.0, 0.0]),
    )
    surface = model.create_entity(
        "IfcSurfaceOfLinearExtrusion",
        SweptCurve=profile,
        Position=axis,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=[0.0, 0.0, 1.0]),
        Depth=4.0,
    )
    representation = model.by_type("IfcShapeRepresentation")[0]
    representation.Items = [surface]
    representation.RepresentationType = "Surface3D"
    element = model.by_type("IfcWall")[0]
    return model.to_string().encode(), element.id()


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4", "IFC4X3_ADD2"])
@pytest.mark.parametrize("tilted", [False, True])
def test_direct_surface_extrusion_matches_world_bounds_and_area(schema: str, tilted: bool) -> None:
    source, element_id = make_surface_fixture(schema, tilted)
    result = ifx_core.extract_ifc(source, "medium")
    mesh = result["geometry"]["elements"][element_id]
    metrics = mesh_metrics(
        np.frombuffer(mesh["vertices"], dtype="<f8").reshape(-1, 3),
        np.frombuffer(mesh["faces"], dtype="<u4").reshape(-1, 3),
    )
    assert metrics["lower"] == pytest.approx([9.0, 20.0, 30.0], abs=1e-6)
    assert metrics["upper"] == pytest.approx(
        [11.0, 24.0, 30.0] if tilted else [11.0, 20.0, 34.0], abs=1e-6
    )
    assert metrics["area_m2"] == pytest.approx(8.0)
    # IfcOpenShell 0.8.5 does not tessellate this direct Surface3D item.
    # The independent reference is a 2 m line swept 4 m, then transformed.
    assert metrics["degenerate_triangles"] == 0
    assert metrics["closed"] is False
