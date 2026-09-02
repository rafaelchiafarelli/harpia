"""process-artifacts epic / jurisdiction-template-selection task -- the
jurisdiction-selected compliance-report shells the `ComplianceReport/` module
emits.

Pure Python, always run. `Process()` is driven directly with a synthetic
ComplianceContext + message set; the pipeline wiring + golden snapshot are
covered by `test_golden.py::test_compliancereport` (which runs with
`jurisdiction: []`, so it snapshots the generic `compliance_report.md` only).

Core guarantee (master plan Section 0a / design-rules Section 6): the same
underlying evidence, a different paperwork shell per jurisdiction -- the SBOM
and traceability sections are byte-identical across jurisdictions, only the
header block changes.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ComplianceReport.ComplianceReport import ComplianceReport
from ComplianceReport import jurisdictions


class _Var:
    def __init__(self, name, is_phi=False):
        self.name = name
        self.is_phi = is_phi
        self.type = "string"


class _Msg:
    def __init__(self, name, variables=(), is_critical=False, table=False):
        self.name = name
        self.variables = list(variables)
        self.is_critical = is_critical
        self.tableName = (name + "_table") if table else ""
        self.isEnum = False


class _Ctx:
    def __init__(self, jurisdiction):
        self.jurisdiction = list(jurisdiction)
        self.project = "acme-pump"
        self.risk_class = "class_c"
        self.topology = "cloud_connected"
        self.phi_handling = "required"


FIXTURE = [
    _Msg("patient_vitals", [_Var("patient_id", True)], table=True),
    _Msg("alarm_event", [_Var("patient_id", True)], is_critical=True, table=True),
]

_EVIDENCE_ANCHOR = "## 1. Software Bill of Materials"


def _emit(dest, jurisdiction):
    err = ComplianceReport(messages=FIXTURE, dest=str(dest),
                           compliance=_Ctx(jurisdiction)).Process()
    assert err is None
    out = os.path.join(str(dest), "generated", "ComplianceReport")
    return {n: open(os.path.join(out, n)).read()
            for n in os.listdir(out) if n.startswith("compliance_report")}


def _evidence(text):
    return text.split(_EVIDENCE_ANCHOR, 1)[1]


def test_one_generic_plus_one_per_jurisdiction(tmp_path):
    reports = _emit(tmp_path, ["FDA", "EU_MDR", "ANVISA"])
    assert set(reports) == {
        "compliance_report.md",
        "compliance_report.fda.md",
        "compliance_report.eu_mdr.md",
        "compliance_report.anvisa.md",
    }


def test_same_evidence_across_jurisdictions(tmp_path):
    reports = _emit(tmp_path, ["FDA", "EU_MDR", "ANVISA"])
    ev = {_evidence(reports[n]) for n in
          ("compliance_report.fda.md", "compliance_report.eu_mdr.md",
           "compliance_report.anvisa.md")}
    assert len(ev) == 1, "evidence section differs across jurisdictions"
    # ... and it is the same evidence the generic report carries
    assert _evidence(reports["compliance_report.md"]) in ev


def test_header_blocks_differ(tmp_path):
    reports = _emit(tmp_path, ["FDA", "EU_MDR", "ANVISA"])
    heads = {n: reports[n].split(_EVIDENCE_ANCHOR, 1)[0] for n in reports}
    assert "21 CFR Part 820" in heads["compliance_report.fda.md"]
    assert "2017/745" in heads["compliance_report.eu_mdr.md"]
    assert "RDC 751/2022" in heads["compliance_report.anvisa.md"]
    # all three header blocks are pairwise distinct
    hset = {heads["compliance_report.fda.md"],
            heads["compliance_report.eu_mdr.md"],
            heads["compliance_report.anvisa.md"]}
    assert len(hset) == 3


def test_eu_mdr_carries_the_tamper_evidence_note(tmp_path):
    reports = _emit(tmp_path, ["FDA", "EU_MDR", "ANVISA"])
    assert "81001-5-1" in reports["compliance_report.eu_mdr.md"]
    assert "tamper-evident" in reports["compliance_report.eu_mdr.md"]
    assert "81001-5-1" not in reports["compliance_report.fda.md"]
    assert "81001-5-1" not in reports["compliance_report.anvisa.md"]


def test_empty_jurisdiction_emits_only_the_generic_report(tmp_path):
    reports = _emit(tmp_path, [])
    assert set(reports) == {"compliance_report.md"}


def test_unknown_token_falls_back_to_generic_shell_with_a_note(tmp_path):
    reports = _emit(tmp_path, ["XX"])
    assert set(reports) == {"compliance_report.md", "compliance_report.xx.md"}
    xx = reports["compliance_report.xx.md"]
    assert "No jurisdiction-specific template for 'XX'" in xx
    # still the same evidence, and the generic framework text
    assert _evidence(xx) == _evidence(reports["compliance_report.md"])
    assert jurisdictions.GENERIC["framework"] in xx


def test_token_match_is_case_and_separator_insensitive(tmp_path):
    reports = _emit(tmp_path, ["eu mdr"])
    assert "compliance_report.eu_mdr.md" in reports
    assert "2017/745" in reports["compliance_report.eu_mdr.md"]


def test_every_report_carries_the_not_legal_advice_disclaimer(tmp_path):
    reports = _emit(tmp_path, ["FDA", "EU_MDR", "ANVISA", "XX"])
    for name, text in reports.items():
        assert "Not legal or regulatory advice" in text, name


def test_no_timestamp_in_any_report(tmp_path):
    reports = _emit(tmp_path, ["FDA", "EU_MDR", "ANVISA"])
    for name, text in reports.items():
        assert "timestamp" not in text, name


def test_rewrite_is_stable(tmp_path):
    _emit(tmp_path, ["FDA"])
    p = os.path.join(str(tmp_path), "generated", "ComplianceReport",
                     "compliance_report.fda.md")
    m1 = os.stat(p).st_mtime_ns
    _emit(tmp_path, ["FDA"])
    assert os.stat(p).st_mtime_ns == m1
