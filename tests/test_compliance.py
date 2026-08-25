"""Tests for Foundation F1 -- ComplianceContext plumbing (Compliance/context.py).

Per initiatives/medical_devices/epics/thread-0-foundation/histories/
ComplianceContext-plumbing.md:
  - Unit: valid config parses; missing file -> strictest default; invalid
    enum value -> hard error.
  - Integration: run the full pipeline with a compliance config present;
    confirm every stage received the context.
  - Acceptance gate: F4 baseline (tests/test_golden.py) is unaffected when
    no config file is present -- covered by test_golden.py itself, since it
    runs tests/run_pipeline.py without HARPIA_COMPLIANCE_CONFIG set and no
    project.harpia.yaml exists at the repo root (missing-file fallback).
"""
import os
import subprocess
import sys

import pytest

from Compliance.context import (
    ComplianceConfigError,
    PhiHandling,
    RiskClass,
    Topology,
    load_compliance_context,
    strictest_profile,
)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")


def _write_yaml(path, text):
    with open(path, "w") as f:
        f.write(text)
    return str(path)


# -- unit: missing file / missing fields -> strictest fallback --------------

def test_missing_file_defaults_to_strictest(tmp_path):
    ctx = load_compliance_context(path=str(tmp_path / "does_not_exist.yaml"))
    strict = strictest_profile()
    assert ctx.risk_class == strict.risk_class
    assert ctx.topology == strict.topology
    assert ctx.phi_handling == strict.phi_handling
    assert ctx.jurisdiction == []


def test_omitted_field_defaults_to_strictest_for_that_field(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "risk_class: class_b\n")
    ctx = load_compliance_context(path=path)
    assert ctx.risk_class == RiskClass.CLASS_B
    # topology/phi_handling were omitted -> each defaults independently
    assert ctx.topology == Topology.CLOUD_CONNECTED
    assert ctx.phi_handling == PhiHandling.REQUIRED


def test_empty_file_defaults_to_strictest(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "")
    ctx = load_compliance_context(path=path)
    strict = strictest_profile()
    assert ctx.risk_class == strict.risk_class
    assert ctx.topology == strict.topology
    assert ctx.phi_handling == strict.phi_handling


# -- unit: a valid, fully-specified config parses correctly -----------------

def test_valid_config_parses(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", """
risk_class: class_a
topology: standalone
phi_handling: opt_in
jurisdiction: [FDA, EU_MDR]
""")
    ctx = load_compliance_context(path=path)
    assert ctx.risk_class == RiskClass.CLASS_A
    assert ctx.topology == Topology.STANDALONE
    assert ctx.phi_handling == PhiHandling.OPT_IN
    assert ctx.jurisdiction == ["FDA", "EU_MDR"]


def test_env_var_override(tmp_path, monkeypatch):
    path = _write_yaml(tmp_path / "custom.harpia.yaml", "risk_class: class_a\n")
    monkeypatch.setenv("HARPIA_COMPLIANCE_CONFIG", path)
    ctx = load_compliance_context()
    assert ctx.risk_class == RiskClass.CLASS_A


# -- unit: invalid/unknown values are a hard error, never silently ignored --

def test_invalid_risk_class_is_hard_error(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "risk_class: not_a_real_class\n")
    with pytest.raises(ComplianceConfigError):
        load_compliance_context(path=path)


def test_invalid_topology_is_hard_error(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "topology: on_the_moon\n")
    with pytest.raises(ComplianceConfigError):
        load_compliance_context(path=path)


def test_invalid_phi_handling_is_hard_error(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "phi_handling: sometimes\n")
    with pytest.raises(ComplianceConfigError):
        load_compliance_context(path=path)


def test_non_list_jurisdiction_is_hard_error(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "jurisdiction: FDA\n")
    with pytest.raises(ComplianceConfigError):
        load_compliance_context(path=path)


def test_non_string_jurisdiction_entries_are_hard_error(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "jurisdiction: [1, 2]\n")
    with pytest.raises(ComplianceConfigError):
        load_compliance_context(path=path)


def test_non_mapping_yaml_is_hard_error(tmp_path):
    path = _write_yaml(tmp_path / "project.harpia.yaml", "- just\n- a\n- list\n")
    with pytest.raises(ComplianceConfigError):
        load_compliance_context(path=path)


# -- integration: every stage in the real pipeline receives the context -----

def test_pipeline_threads_compliance_through_every_stage(tmp_path):
    config_path = _write_yaml(tmp_path / "project.harpia.yaml", """
risk_class: class_a
topology: standalone
phi_handling: opt_in
jurisdiction: [ANVISA]
""")
    out = tmp_path / "artifacts"
    out.mkdir()

    env = dict(os.environ)
    env["HARPIA_COMPLIANCE_CONFIG"] = config_path

    result = subprocess.run(
        [sys.executable, RUNNER, str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        "pipeline runner failed:\n" + result.stdout + result.stderr
    )

    smoke_path = out / "compliance_smoke.txt"
    assert smoke_path.exists(), "run_pipeline.py did not emit compliance_smoke.txt"
    lines = smoke_path.read_text().splitlines()
    assert lines, "no stages recorded in compliance_smoke.txt"
    for line in lines:
        assert line.endswith(": True"), (
            "a stage did not receive the exact ComplianceContext instance: {}".format(line)
        )
