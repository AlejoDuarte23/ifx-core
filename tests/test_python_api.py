import json

import ifx_core

MINIMAL_IFC = b"""ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,#2);
#2=IFCUNITASSIGNMENT((#3));
#3=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
ENDSEC;
END-ISO-10303-21;
"""


def test_model_data_returns_native_python_objects() -> None:
    data = ifx_core.model_data(MINIMAL_IFC)

    assert data["schema"] == "IFC4"
    assert data["entity_count"] == 3
    assert data["spatial"]["project_id"] == 1
    assert data["spatial"]["roots"][0]["express_id"] == 1
    assert data["units"]["assignment_id"] == 2
    assert data["units"]["by_type"]["LENGTHUNIT"]["symbol"] == "m"
    assert data["openings"] == {
        "voids": [],
        "fills": [],
        "openings_by_element": {},
        "elements_by_opening": {},
        "fillings_by_opening": {},
        "openings_by_filling": {},
    }
    assert data["materials"]["associations"] == []


def test_json_api_matches_native_api() -> None:
    assert json.loads(ifx_core.model_data_json(MINIMAL_IFC)) == ifx_core.model_data(MINIMAL_IFC)
