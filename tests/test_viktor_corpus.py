import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from test_ifcopenshell_parity import (
    assert_classification_parity,
    assert_connection_parity,
    assert_document_parity,
    assert_georeferencing_parity,
    assert_group_parity,
    assert_material_parity,
    assert_opening_parity,
    assert_relationship_parity,
    assert_spatial_parity,
)

import ifx_core

try:
    import ifcopenshell
except ModuleNotFoundError:
    pytest.skip("IfcOpenShell is required for corpus tests", allow_module_level=True)

MANIFEST_PATH = Path(__file__).with_name("viktor_corpus.json")
MANIFEST: dict[str, Any] = json.loads(MANIFEST_PATH.read_text())


@pytest.fixture(params=MANIFEST["models"], ids=lambda model: model["name"])
def corpus_model(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    if os.environ.get("IFX_RUN_REMOTE_CORPUS") != "1":
        pytest.skip("set IFX_RUN_REMOTE_CORPUS=1 to download the VIKTOR IFC corpus")

    model = request.param
    encoded_name = urllib.parse.quote(model["name"])
    url = (
        "https://raw.githubusercontent.com/viktor-platform/ifc-sample-models/"
        f"{MANIFEST['commit']}/sample-models/{encoded_name}"
    )
    target = tmp_path / model["name"]
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())
    assert hashlib.sha256(target.read_bytes()).hexdigest() == model["sha256"]
    return target


@pytest.mark.corpus
def test_viktor_model_matches_ifcopenshell(corpus_model: Path) -> None:
    source = corpus_model.read_bytes()
    model = ifcopenshell.open(corpus_model)
    data = ifx_core.model_data(source)

    assert_relationship_parity(model, data)
    assert_spatial_parity(model, data)
    assert_material_parity(model, data)
    assert_opening_parity(model, data)
    assert_classification_parity(model, data)
    assert_document_parity(model, data)
    assert_group_parity(model, data)
    assert_connection_parity(model, data)
    assert_georeferencing_parity(model, data)
