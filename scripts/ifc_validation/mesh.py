import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Tolerances:
    bounds_m: float = 0.002
    area_relative: float = 0.02
    volume_relative: float = 0.02

    def __post_init__(self) -> None:
        for value in (self.bounds_m, self.area_relative, self.volume_relative):
            if not math.isfinite(value) or value < 0:
                raise ValueError("geometry tolerances must be finite and nonnegative")


def mesh_metrics(vertices: np.ndarray, faces: np.ndarray) -> dict[str, object]:
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices):
        raise ValueError("mesh needs nonempty XYZ vertices")
    if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces):
        raise ValueError("mesh needs nonempty triangle indices")
    if not np.isfinite(vertices).all():
        raise ValueError("mesh contains nonfinite vertices")
    if not np.issubdtype(faces.dtype, np.integer):
        raise ValueError("triangle indices must be integers")
    if faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("triangle index is outside the vertex array")
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    centre = (lower + upper) / 2
    area = 0.0
    volume = 0.0
    degenerate = 0
    for start in range(0, len(faces), 65536):
        triangles = vertices[faces[start : start + 65536]] - centre
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        double_area = np.linalg.norm(cross, axis=1)
        area += float(double_area.sum()) / 2
        degenerate += int(np.count_nonzero(double_area == 0))
        volume += float(np.einsum("ij,ij->i", triangles[:, 0], cross).sum()) / 6

    # Weld for topology only. Different tessellators can duplicate a corner for
    # each face; this must not make a geometrically closed solid look open.
    _, welded = np.unique(vertices, axis=0, return_inverse=True)
    indices = welded[faces]
    edges = np.concatenate((indices[:, [0, 1]], indices[:, [1, 2]], indices[:, [2, 0]]))
    sorted_edges = np.sort(edges, axis=1)
    _, inverse, counts = np.unique(sorted_edges, axis=0, return_inverse=True, return_counts=True)
    directions = np.where(edges[:, 0] < edges[:, 1], 1, -1)
    balance = np.bincount(inverse, weights=directions)
    closed = bool(np.all(counts == 2) and np.all(balance == 0) and degenerate == 0)
    if not math.isfinite(area) or not math.isfinite(volume):
        raise ValueError("mesh area or volume is not finite")
    return {
        "lower": lower.tolist(),
        "upper": upper.tolist(),
        "area_m2": area,
        "volume_m3": abs(volume) if closed else None,
        "closed": closed,
        "vertices": len(vertices),
        "triangles": len(faces),
        "degenerate_triangles": degenerate,
    }


def compare_metrics(
    expected: dict[str, object], actual: dict[str, object], limits: Tolerances
) -> list[str]:
    failures: list[str] = []
    for key in ("lower", "upper"):
        if not np.allclose(actual[key], expected[key], rtol=0, atol=limits.bounds_m):
            failures.append(f"{key} bounds differ")
    if not math.isclose(
        float(actual["area_m2"]),
        float(expected["area_m2"]),
        rel_tol=limits.area_relative,
        abs_tol=limits.bounds_m**2,
    ):
        failures.append("surface area differs")
    if expected["closed"]:
        if not actual["closed"]:
            failures.append("reference solid is closed but candidate mesh is open or misoriented")
        elif not math.isclose(
            float(actual["volume_m3"]),
            float(expected["volume_m3"]),
            rel_tol=limits.volume_relative,
            abs_tol=limits.bounds_m**3,
        ):
            failures.append("solid volume differs")
    if actual["degenerate_triangles"]:
        failures.append("candidate mesh contains zero-area triangles")
    return failures
