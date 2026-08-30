"""fhir-facade epic -- the hand-mapped HeartRateReading -> FHIR Observation
worked example validates against the vendored FHIR R4 schema.

Design-validation only: no FhirAdapter/ code exists (that's a follow-on
epic). Pure Python, always runs, standard library only -- structural checks
against worked-example/fhir.schema.json's Observation definition, the same
posture test_sbom_emission.py takes against the vendored CycloneDX schema.
No jsonschema dependency, no network.
"""
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
WE = os.path.join(REPO_ROOT, "Initiatives", "medical_devices", "epics",
                  "fhir-facade-done", "worked-example")
SCHEMA_PATH = os.path.join(WE, "fhir.schema.json")
EXAMPLE_PATH = os.path.join(WE, "heartrate_observation.example.json")

CONFIDENTIALITY_SYS = "http://terminology.hl7.org/CodeSystem/v3-Confidentiality"
OBS_CATEGORY_SYS = "http://terminology.hl7.org/CodeSystem/observation-category"
DEVICE_IDENT_SYS = "https://harpia.dev/fhir/identifier/default/device"


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def example():
    with open(EXAMPLE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def observation_def(schema):
    return schema["definitions"]["Observation"]


def test_vendored_schema_is_fhir_r4(schema):
    assert schema.get("id") == "http://hl7.org/fhir/json-schema/4.0"
    assert "Observation" in schema["definitions"]


def test_example_is_an_observation(example):
    assert example["resourceType"] == "Observation"


def test_fhir_required_elements_present(example, observation_def):
    for key in observation_def["required"]:          # -> ["code", "resourceType"]
        assert key in example, "missing FHIR-required Observation element: " + key


def test_only_declared_observation_properties_used(example, observation_def):
    declared = set(observation_def["properties"])
    unknown = sorted(k for k in example if k not in declared)
    assert not unknown, "example uses non-Observation properties: " + repr(unknown)


def test_status_is_a_valid_code(example, observation_def):
    assert example["status"] in observation_def["properties"]["status"]["enum"]
    assert example["status"] == "final"


def test_effective_datetime_matches_schema_pattern(example, observation_def):
    import re
    pat = observation_def["properties"]["effectiveDateTime"]["pattern"]
    assert re.match(pat, example["effectiveDateTime"])


def test_heart_rate_carries_the_loinc_code(example):
    loinc = [c for c in example["code"]["coding"]
             if c.get("system") == "http://loinc.org"]
    assert loinc, "no LOINC coding on Observation.code"
    assert loinc[0]["code"] == "8867-4"              # LOINC: Heart rate


def test_value_quantity_uses_ucum(example):
    q = example["valueQuantity"]
    assert q["system"] == "http://unitsofmeasure.org"
    assert q["code"] == "/min"
    assert isinstance(q["value"], (int, float)) and not isinstance(q["value"], bool)


def test_category_is_vital_signs(example):
    codes = {c.get("code")
             for cc in example["category"] for c in cc.get("coding", [])
             if c.get("system") == OBS_CATEGORY_SYS}
    assert "vital-signs" in codes


def test_phi_maps_to_whole_resource_confidentiality(example):
    """design doc §3/§8: any phi field -> the whole resource gets a
    meta.security Confidentiality label (FHIR has no field-level one)."""
    conf = [c for c in example["meta"]["security"]
            if c.get("system") == CONFIDENTIALITY_SYS]
    assert conf, "no v3-Confidentiality security label (the phi obligation)"
    assert conf[0]["code"] == "R"


def test_device_id_is_reference_by_identifier(example):
    """design doc §6: no auto-split into a separate/contained Device."""
    assert "contained" not in example
    assert "reference" not in example["device"], \
        "device_id must not be a resolved Reference.reference"
    ident = example["device"]["identifier"]
    assert ident["system"] == DEVICE_IDENT_SYS       # project-namespaced (design doc §7)
    assert ident["value"]


def test_no_invented_subject(example):
    """Rule 5 / design doc §2: the HeartRateReading form used here carries
    no patient id, so the example must not fabricate an Observation.subject.
    (mapping-notes.md records this as a known gap.)"""
    assert "subject" not in example


def test_mapping_notes_present():
    assert os.path.isfile(os.path.join(WE, "mapping-notes.md"))
    assert os.path.isfile(os.path.join(WE, "VENDORED.md"))
