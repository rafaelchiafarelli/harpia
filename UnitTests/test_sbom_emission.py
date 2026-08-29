"""process-artifacts epic / sbom-emission task -- the ComplianceReport/ module
and its CycloneDX 1.5 SBOM.

Pure Python, always run. `ComplianceReport.Process()` is exercised directly
(no generated C++ project needed -- the SBOM is schema-independent); the
pipeline wiring is covered by `test_golden.py::test_compliancereport` and the
`compliance_smoke.txt` check in `test_compliance.py`.

Structural validation is done against the vendored
`ComplianceReport/schema/bom-1.5.schema.json` using the standard library only
-- the schema's own `required` arrays and `enum`s -- so there is no
`jsonschema` runtime dependency (see the task file).
"""
import json
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ComplianceReport.ComplianceReport import ComplianceReport, SBOM_FILENAME
from ComplianceReport import components
from Compliance.context import (ComplianceContext, RiskClass, Topology,
                                PhiHandling)

SCHEMA_PATH = os.path.join(REPO_ROOT, "ComplianceReport", "schema",
                           "bom-1.5.schema.json")


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _context(jurisdiction=("fda", "eu_mdr")):
    return ComplianceContext(
        risk_class=RiskClass.CLASS_C,
        topology=Topology.CLOUD_CONNECTED,
        phi_handling=PhiHandling.REQUIRED,
        jurisdiction=list(jurisdiction),
        project="acme-pump",
    )


def _emit(dest, compliance=None, crypto_backend=None):
    if crypto_backend is not None:
        md = os.path.join(dest, "build_metadata")
        os.makedirs(md, exist_ok=True)
        with open(os.path.join(md, "crypto_backend.json"), "w") as f:
            json.dump({"crypto_backend": crypto_backend, "fips_validated": False}, f)
    err = ComplianceReport(messages=[], dest=str(dest),
                           compliance=compliance).Process()
    assert err is None
    bom_path = os.path.join(str(dest), "generated", "ComplianceReport",
                            SBOM_FILENAME)
    with open(bom_path) as f:
        return json.load(f), bom_path


# -- schema-structural validation (stdlib, against the vendored schema) ------

def test_top_level_required_fields_present(tmp_path, schema):
    bom, _ = _emit(tmp_path, _context())
    for key in schema["required"]:                       # bomFormat, specVersion, version
        assert key in bom, "missing top-level required field {!r}".format(key)
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.5"
    assert isinstance(bom["version"], int)


def test_metadata_component_and_tool(tmp_path, schema):
    bom, _ = _emit(tmp_path, _context())
    comp = bom["metadata"]["component"]
    comp_required = schema["definitions"]["component"]["required"]   # type, name
    for key in comp_required:
        assert key in comp
    comp_type_enum = schema["definitions"]["component"]["properties"]["type"]["enum"]
    assert comp["type"] in comp_type_enum
    assert comp["type"] == "application"
    assert comp["name"] == "acme-pump"
    assert bom["metadata"]["tools"][0]["name"] == "harpia"


def test_every_component_valid_and_versioned(tmp_path, schema):
    bom, _ = _emit(tmp_path, _context())
    comp_required = schema["definitions"]["component"]["required"]
    comp_type_enum = schema["definitions"]["component"]["properties"]["type"]["enum"]
    names = set()
    for c in bom["components"]:
        for key in comp_required:
            assert key in c, "component missing {!r}: {}".format(key, c)
        assert c["type"] in comp_type_enum
        assert c["version"], "component {!r} has an empty version".format(c["name"])
        names.add(c["name"])
    # the declared manifest is all present
    expected = {n for n, *_ in components.VENDORED} | {n for n, *_ in components.ENVIRONMENT}
    assert names == expected


def test_components_sorted_and_stable(tmp_path):
    bom, _ = _emit(tmp_path, _context())
    names = [c["name"] for c in bom["components"]]
    assert names == sorted(names)


# -- harpia:* properties carry the ComplianceContext values -----------------

def test_harpia_properties_reflect_context(tmp_path):
    bom, _ = _emit(tmp_path, _context(jurisdiction=("fda", "anvisa")),
                   crypto_backend="openssl-fips")
    props = {p["name"]: p["value"] for p in bom["metadata"]["properties"]}
    assert props["harpia:risk_class"] == "class_c"
    assert props["harpia:topology"] == "cloud_connected"
    assert props["harpia:phi_handling"] == "required"
    assert props["harpia:crypto_backend"] == "openssl-fips"
    assert props["harpia:jurisdiction"] == "fda,anvisa"


def test_jurisdiction_is_inert_metadata_only(tmp_path):
    # master plan Section 0a: jurisdiction[] never changes SBOM *content*,
    # only the one metadata property.
    bom_a, _ = _emit(tmp_path / "a", _context(jurisdiction=("fda",)))
    bom_b, _ = _emit(tmp_path / "b", _context(jurisdiction=("eu_mdr", "anvisa")))
    strip = lambda b: (b["components"], b["metadata"]["component"])
    assert strip(bom_a) == strip(bom_b)
    pa = {p["name"]: p["value"] for p in bom_a["metadata"]["properties"]}
    pb = {p["name"]: p["value"] for p in bom_b["metadata"]["properties"]}
    assert pa["harpia:jurisdiction"] == "fda"
    assert pb["harpia:jurisdiction"] == "eu_mdr,anvisa"


def test_crypto_backend_unknown_without_metadata_file(tmp_path):
    bom, _ = _emit(tmp_path, _context())          # no crypto_backend.json written
    props = {p["name"]: p["value"] for p in bom["metadata"]["properties"]}
    assert props["harpia:crypto_backend"] == "unknown"


def test_runs_without_a_compliance_context(tmp_path, schema):
    bom, _ = _emit(tmp_path, None)
    for key in schema["required"]:
        assert key in bom
    props = {p["name"]: p["value"] for p in bom["metadata"]["properties"]}
    assert props["harpia:risk_class"] == ""
    assert props["harpia:jurisdiction"] == ""
    assert bom["metadata"]["component"]["name"] == "default"


# -- vendored versions come from the checked-in VENDORED.md files -----------

def test_vendored_versions_resolved_from_repo(tmp_path):
    bom, _ = _emit(tmp_path, _context())
    by_name = {c["name"]: c for c in bom["components"]}
    assert by_name["asio"]["version"] == "1.30.2"
    assert by_name["sqlite"]["version"] == "3.46.1"
    assert by_name["tinyxml2"]["version"] == "10.0.0"
    assert by_name["crow"]["version"] == "1.3.2"
    # a real version yields a purl and license/source refs
    assert by_name["asio"]["purl"] == "pkg:github/asio@1.30.2"
    assert by_name["sqlite"]["licenses"][0]["license"]["name"]
    assert by_name["tinyxml2"]["externalReferences"][0]["url"].startswith("http")


def test_missing_vendored_md_degrades_to_unknown():
    assert components.vendored_version("does-not-exist") == "unknown"
    assert components.environment_version([["definitely-not-a-real-binary"]]) == "unknown"


# -- write-if-different -----------------------------------------------------

def test_rewrite_is_stable_when_nothing_changed(tmp_path, monkeypatch):
    # pin the wall-clock timestamp so two emits are byte-identical -- then
    # write_if_different must leave the file (and its mtime) untouched.
    import ComplianceReport.ComplianceReport as mod
    monkeypatch.setattr(mod, "_rfc3339_now", lambda: "2026-01-02T03:04:05Z")

    _, bom_path = _emit(tmp_path, _context(), crypto_backend="openssl")
    mtime1 = os.stat(bom_path).st_mtime_ns
    time.sleep(0.01)
    ComplianceReport(messages=[], dest=str(tmp_path),
                     compliance=_context()).Process()
    assert os.stat(bom_path).st_mtime_ns == mtime1
