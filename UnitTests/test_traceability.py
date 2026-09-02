"""process-artifacts epic / traceability-matrix task -- the requirement ->
code -> evidence matrix the `ComplianceReport/` module emits alongside the
SBOM.

Pure Python, always run. `ComplianceReport.Process()` is driven directly with
a synthetic message set mirroring the `HarpiaTest` fixtures
(`patient_vitals` mixed-phi table, `alarm_event` critical+phi table,
`lab_result` all-phi table-less); the pipeline wiring + golden snapshot are
covered by `test_golden.py::test_compliancereport`.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ComplianceReport.ComplianceReport import (ComplianceReport,
                                               TRACEABILITY_JSON,
                                               TRACEABILITY_MD)
from ComplianceReport.requirements import REQUIREMENTS, REQUIREMENTS_BY_ID


class _Var:
    def __init__(self, name, is_phi=False):
        self.name = name
        self.is_phi = is_phi
        self.type = "string"


class _Msg:
    def __init__(self, name, variables=(), is_critical=False, table=False,
                 is_enum=False):
        self.name = name
        self.variables = list(variables)
        self.is_critical = is_critical
        self.tableName = (name + "_table") if table else ""
        self.isEnum = is_enum


FIXTURE = [
    _Msg("patient_vitals",
         [_Var("patient_id", True), _Var("heart_rate", True), _Var("device_note")],
         table=True),
    _Msg("alarm_event",
         [_Var("patient_id", True), _Var("alarm_type"), _Var("severity")],
         is_critical=True, table=True),
    _Msg("lab_result",
         [_Var("subject_ref", True), _Var("analyte_code", True),
          _Var("value_scaled", True), _Var("reference_high", True)],
         table=False),
    _Msg("users", [_Var("name"), _Var("id")], table=True),   # no phi, not critical
    _Msg("Color", [], is_enum=True),
]

_N_PHI_REQS   = len([r for r in REQUIREMENTS if r.applies_to == "phi_field"])
_N_PHI_TBL    = len([r for r in REQUIREMENTS if r.applies_to == "phi_field_table"])
_N_CRIT_REQS  = len([r for r in REQUIREMENTS if r.applies_to == "critical_message"])
_N_PROJ_REQS  = len([r for r in REQUIREMENTS if r.applies_to == "project"])


def _emit(dest, messages=FIXTURE):
    err = ComplianceReport(messages=messages, dest=str(dest),
                           compliance=None).Process()
    assert err is None
    out = os.path.join(str(dest), "generated", "ComplianceReport")
    with open(os.path.join(out, TRACEABILITY_JSON)) as f:
        data = json.load(f)
    with open(os.path.join(out, TRACEABILITY_MD)) as f:
        md = f.read()
    return data["rows"], md


def test_every_row_is_well_formed(tmp_path):
    rows, _ = _emit(tmp_path)
    assert rows
    for r in rows:
        assert r["construct"], r
        assert r["requirement_id"] in REQUIREMENTS_BY_ID, r
        assert r["rule_ref"] and r["requirement"] and r["mechanism"], r
        assert r["evidence"] and all(e for e in r["evidence"]), r


def test_row_count_matches_the_catalog(tmp_path):
    rows, _ = _emit(tmp_path)
    n_phi = sum(1 for m in FIXTURE if not m.isEnum
                for v in m.variables if v.is_phi)
    n_phi_tbl = sum(1 for m in FIXTURE if not m.isEnum and m.tableName
                    for v in m.variables if v.is_phi)
    n_crit = sum(1 for m in FIXTURE if not m.isEnum and m.is_critical)
    expected = (n_phi * _N_PHI_REQS + n_phi_tbl * _N_PHI_TBL
                + n_crit * _N_CRIT_REQS + _N_PROJ_REQS)
    assert len(rows) == expected


def test_table_less_phi_field_has_redaction_but_no_db_rows(tmp_path):
    rows, _ = _emit(tmp_path)
    lab = [r for r in rows if r["construct"].startswith("lab_result.")]
    ids = {r["requirement_id"] for r in lab}
    assert "R1-RED" in ids
    assert "R1-ENC" not in ids and "R5-AUDIT-DB" not in ids
    # the table-bearing phi field does get the DB rows
    pv = {r["requirement_id"] for r in rows
          if r["construct"] == "patient_vitals.patient_id"}
    assert {"R1-RED", "R1-ENC", "R5-AUDIT-DB"} <= pv


def test_critical_message_rows(tmp_path):
    rows, _ = _emit(tmp_path)
    ae = {r["requirement_id"] for r in rows if r["construct"] == "alarm_event"}
    assert ae == {"R4A-ORDERED", "R3-INTEGRITY"}


def test_spot_checks_against_known_evidence(tmp_path):
    rows, _ = _emit(tmp_path)
    by_key = {(r["construct"], r["requirement_id"]): r for r in rows}
    enc = by_key[("patient_vitals.patient_id", "R1-ENC")]
    assert any("test_stage8_db.py" in e for e in enc["evidence"])
    ordered = by_key[("alarm_event", "R4A-ORDERED")]
    assert any("test_critical_delivery_roundtrip.py" in e for e in ordered["evidence"])


def test_non_annotated_message_contributes_no_rows(tmp_path):
    rows, _ = _emit(tmp_path)
    assert not [r for r in rows if r["construct"].startswith("users")]
    assert not [r for r in rows if r["construct"].startswith("Color")]


def test_rows_are_sorted_and_deterministic(tmp_path):
    rows1, md1 = _emit(tmp_path / "a")
    rows2, md2 = _emit(tmp_path / "b")
    assert rows1 == rows2
    assert md1 == md2
    keys = [(r["construct"], r["requirement_id"]) for r in rows1]
    assert keys == sorted(keys)


def test_md_has_one_table_row_per_json_row(tmp_path):
    rows, md = _emit(tmp_path)
    body = md.split("|---|", 1)[1]
    table_lines = [ln for ln in body.splitlines() if ln.startswith("| `")]
    assert len(table_lines) == len(rows)


def test_no_timestamp_in_output(tmp_path):
    _, md = _emit(tmp_path)
    with open(os.path.join(str(tmp_path), "generated", "ComplianceReport",
                           TRACEABILITY_JSON)) as f:
        raw = f.read()
    assert "timestamp" not in raw and "timestamp" not in md


def test_rewrite_is_stable(tmp_path):
    _emit(tmp_path)
    p = os.path.join(str(tmp_path), "generated", "ComplianceReport", TRACEABILITY_JSON)
    m1 = os.stat(p).st_mtime_ns
    _emit(tmp_path)
    assert os.stat(p).st_mtime_ns == m1
