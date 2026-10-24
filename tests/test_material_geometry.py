import json

import pytest
from material_fixture import material_window

import ifx_core


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4"])
def test_frame_and_glass_materials_survive_native_export(schema: str) -> None:
    source, window_id = material_window(schema)
    export = ifx_core.geometry_data_buffers(source, "medium")
    assert export["element_count"] == 1
    window = export["elements"][window_id]
    groups = window["material_groups"]
    assert len(groups) == 3
    assert [group["triangle_count"] for group in groups] == [12, 12, 12]
    assert [group["triangle_start"] for group in groups] == [0, 12, 24]
    assert groups[0]["color"] == pytest.approx([0.9, 0.9, 0.9, 1.0])
    assert groups[1]["color"] == pytest.approx([0.7, 0.3, 0.24, 1.0])
    assert groups[2]["color"] == pytest.approx([0.1, 0.1, 0.1, 0.12])
    assert sum(group["triangle_count"] for group in groups) == len(window["faces"]) // 12
    json_export = json.loads(ifx_core.geometry_data_json(source, "medium"))
    for encoded, native in zip(
        json_export["elements"][str(window_id)]["material_groups"], groups, strict=True
    ):
        assert encoded["triangle_start"] == native["triangle_start"]
        assert encoded["triangle_count"] == native["triangle_count"]
        assert encoded["color"] == pytest.approx(native["color"])
