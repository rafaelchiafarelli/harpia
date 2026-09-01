"""versioning epic / task 2 -- git fork-lineage in ComplianceReport's bom.json.

Pure Python. The bom.json property path is exercised directly through
`ComplianceReport.Process()` (no generated C++ project needed); the cases
that need a real `git` binary are skipif-gated, same discipline as the
protoc/cmake behavioural tests. The pipeline wiring + golden normalization
are covered by `test_golden.py::test_compliancereport`.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ComplianceReport.ComplianceReport as mod
from ComplianceReport.ComplianceReport import ComplianceReport, SBOM_FILENAME

needs_git = pytest.mark.skipif(shutil.which("git") is None,
                               reason="git binary not on PATH")

_CONTEXT_KEYS = ["harpia:risk_class", "harpia:topology", "harpia:phi_handling",
                 "harpia:crypto_backend", "harpia:jurisdiction"]
_GIT_KEYS = ["harpia:git_commit", "harpia:git_ref", "harpia:git_dirty",
             "harpia:git_describe", "harpia:git_origin_url",
             "harpia:git_parent_commit"]


def _emit(dest):
    err = ComplianceReport(messages=[], dest=str(dest), compliance=None).Process()
    assert err is None
    with open(os.path.join(str(dest), "generated", "ComplianceReport",
                           SBOM_FILENAME)) as f:
        return json.load(f)


def _props(bom):
    return {p["name"]: p["value"] for p in bom["metadata"]["properties"]}


def _fake_state(**over):
    st = {"commit": "unknown", "ref": "unknown", "dirty": "unknown",
          "describe": "unknown", "origin_url": "unknown",
          "parent_commit": "unknown"}
    st.update(over)
    return st


# -- property shape / values (always run, git read monkeypatched) ----------

def test_six_git_properties_after_the_context_pairs(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_collect_git_state", lambda *a, **k: _fake_state(
        commit="a" * 40, ref="main", dirty=False, describe="v1.2.3",
        origin_url="https://example.com/x.git", parent_commit="b" * 40))
    bom = _emit(tmp_path)
    names = [p["name"] for p in bom["metadata"]["properties"]]
    assert names[:5] == _CONTEXT_KEYS
    assert names[5:] == _GIT_KEYS               # appended, in order, after
    p = _props(bom)
    assert p["harpia:git_commit"] == "a" * 40
    assert p["harpia:git_ref"] == "main"
    assert p["harpia:git_dirty"] == "false"
    assert p["harpia:git_describe"] == "v1.2.3"
    assert p["harpia:git_origin_url"] == "https://example.com/x.git"
    assert p["harpia:git_parent_commit"] == "b" * 40


def test_dirty_true_serializes_as_the_string_true(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_collect_git_state",
                        lambda *a, **k: _fake_state(dirty=True))
    assert _props(_emit(tmp_path))["harpia:git_dirty"] == "true"


def test_graceful_absence_is_six_unknowns(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_collect_git_state", lambda *a, **k: _fake_state())
    p = _props(_emit(tmp_path))
    for key in _GIT_KEYS:
        assert p[key] == "unknown"


def test_bom_still_structurally_valid_with_git_props(tmp_path, monkeypatch):
    # the new props must not break the sbom-emission structural contract
    monkeypatch.setattr(mod, "_collect_git_state", lambda *a, **k: _fake_state())
    bom = _emit(tmp_path)
    for prop in bom["metadata"]["properties"]:
        assert set(prop) == {"name", "value"}
        assert isinstance(prop["name"], str) and isinstance(prop["value"], str)


def test_tool_version_bumped_to_0_2_0(tmp_path):
    assert mod.HARPIA_TOOL_VERSION == "0.2.0"
    assert _emit(tmp_path)["metadata"]["tools"][0]["version"] == "0.2.0"


def test_no_git_repo_still_generates(tmp_path, monkeypatch):
    # acceptance gate: cwd not under any repo -> real collect_git_state()
    # returns all-"unknown", generation succeeds, all six props present.
    proj = tmp_path / "nogit"
    proj.mkdir()
    monkeypatch.chdir(proj)
    p = _props(_emit(tmp_path / "out"))
    for key in _GIT_KEYS:
        assert p[key] == "unknown"


# -- against a real git repo ---------------------------------------------

@needs_git
def test_stamps_this_repos_head(tmp_path):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    assert _props(_emit(tmp_path))["harpia:git_commit"] == head


@needs_git
def test_fork_lineage_traceable_to_parent(tmp_path, monkeypatch):
    def g(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True, text=True)

    upstream = tmp_path / "upstream.git"
    upstream.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", str(upstream)], check=True)

    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(upstream), str(work)],
                   check=True, capture_output=True)
    g(work, "config", "user.email", "t@example.com")
    g(work, "config", "user.name", "Test")
    g(work, "config", "commit.gpgsign", "false")
    (work / "a.txt").write_text("1\n")
    g(work, "add", "a.txt")
    g(work, "commit", "-qm", "base")
    g(work, "push", "-q", "origin", "HEAD")
    g(work, "remote", "set-head", "origin", "-a")     # make origin/HEAD resolve

    base = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    (work / "b.txt").write_text("2\n")
    g(work, "add", "b.txt")
    g(work, "commit", "-qm", "local change")

    monkeypatch.chdir(work)
    p = _props(_emit(tmp_path / "out"))
    assert p["harpia:git_commit"] != base
    assert p["harpia:git_parent_commit"] == base      # traceable to the parent
    assert p["harpia:git_origin_url"] == str(upstream)
