import json

import ifcopenshell
import pytest
from ifcopenshell.util.element import get_type
from type_fixtures import make_type_fixture

import ifx_core
from scripts.ifc_validation.checks import check_entities
from scripts.ifc_validation.fixtures import SCHEMAS


@pytest.mark.parametrize("schema", SCHEMAS)
def test_linked_type_keeps_source_identity_attributes_and_existing_inherited_properties(
    schema: str,
) -> None:
    source, ids = make_type_fixture(schema)
    model = ifcopenshell.file.from_string(source.decode())
    source_type = get_type(model.by_id(ids["duct"]))
    data = ifx_core.model_data(source)
    types = data["object_types"]
    assert types["types_by_element"][ids["duct"]] == [source_type.id()]
    definition = types["definitions"][source_type.id()]
    assert definition["ifc_type"] == source_type.is_a()
    assert definition["global_id"] == source_type.GlobalId
    assert definition["name"] == source_type.Name
    assert definition["description"] == source_type.Description
    attributes = {item["name"]: item["value"] for item in definition["attributes"]}
    for name in ["ApplicableOccurrence", "Tag", "ElementType", "PredefinedType"]:
        assert attributes[name] == getattr(source_type, name)
    assert "Name" not in attributes
    assert "HasPropertySets" not in attributes
    entities = ifx_core.entity_data(source)
    assert check_entities(model, entities)["status"] == "pass"
    values = entities["entities"][ids["duct"]]["property_sets"][0]["properties"]
    assert sum(prop["name"] == "TypeCode" for prop in values) == 1
    assert any(prop["name"] == "SourceLength" for prop in values)
    assert json.loads(ifx_core.model_data_json(source))["object_types"] == json.loads(
        json.dumps(types)
    )


@pytest.mark.parametrize("schema", SCHEMAS)
def test_shared_types_are_exported_once_and_do_not_require_property_sets(schema: str) -> None:
    source, ids = make_type_fixture(schema)
    model = ifcopenshell.file.from_string(source.decode())
    source_type = model.by_id(ids["type"])
    source_type.HasPropertySets = None
    source_type.Name = None
    source_type.Description = None
    duct = model.create_entity(model.by_id(ids["duct"]).is_a(), GlobalId=ifcopenshell.guid.new())
    relation = model.by_id(ids["relation"])
    relation.RelatedObjects = [model.by_id(ids["duct"]), duct]
    model.create_entity(
        "IfcRelDefinesByType",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[duct],
        RelatingType=source_type,
    )
    types = ifx_core.model_data(model.to_string().encode())["object_types"]
    assert len(types["definitions"]) == 1
    assert types["types_by_element"] == {
        ids["duct"]: [source_type.id()],
        duct.id(): [source_type.id()],
    }
    assert types["definitions"][source_type.id()]["name"] is None
    assert types["definitions"][source_type.id()]["description"] is None


@pytest.mark.parametrize("schema", SCHEMAS)
def test_missing_type_is_not_replaced_with_invented_metadata(schema: str) -> None:
    source, ids = make_type_fixture(schema)
    model = ifcopenshell.file.from_string(source.decode())
    relation = model.by_id(ids["relation"])
    broken = model.to_string().replace(
        relation.to_string(), relation.to_string().replace(f"#{ids['type']}", "#999999")
    )
    types = ifx_core.model_data(broken.encode())["object_types"]
    assert ids["duct"] not in types["types_by_element"]
