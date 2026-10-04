"""multi-system-reference / load-harness task 3 -- report.py.

The hand-written fixture set (UnitTests/load_report_fixture/: three clients'
JSONL with every record type, an error mix, a partial last line, a non-report
.log, and a spawn.json with one crash) must produce exactly
expected_summary.json. The expected numbers were worked out by hand (nearest-
rank percentiles, ops/s over the 21 s run, 10 s timeline buckets).
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
FIXTURE = os.path.join(HERE, "load_report_fixture")
REPORT = os.path.join(REPO_ROOT, "HarpiaTest", "app_example", "multi_system", "load", "report.py")


def _run(out):
    return subprocess.run([sys.executable, REPORT, out], capture_output=True, text=True, timeout=60)


def test_fixture_produces_expected_summary(tmp_path):
    out = str(tmp_path / "run")
    shutil.copytree(FIXTURE, out)
    os.remove(os.path.join(out, "expected_summary.json"))
    r = _run(out)
    assert r.returncode == 0, r.stderr
    with open(os.path.join(out, "summary.json")) as f:
        got = json.load(f)
    with open(os.path.join(FIXTURE, "expected_summary.json")) as f:
        want = json.load(f)
    assert got == want
    with open(os.path.join(out, "summary.md")) as f:
        md = f.read()
    assert md == r.stdout
    assert "| edge | create | 5 | 0.4000 | 0.238 | 250 | 10000 | 10000 | 10000 |" in md
    assert "spawned 3, crashed 1: hh-a" in md


def test_empty_and_missing_dirs(tmp_path):
    r = _run(str(tmp_path))
    assert r.returncode == 0, r.stderr
    with open(os.path.join(str(tmp_path), "summary.json")) as f:
        s = json.load(f)
    assert s["records"] == 0 and s["ops"] == {} and s["timeline"] == []
    assert _run(str(tmp_path / "nope")).returncode == 2
