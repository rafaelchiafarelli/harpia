"""Golden-file regression test for the harpia front-end pipeline.

Runs the pipeline on HarpiaTest/test.harpia (via tests/run_pipeline.py in a
fresh subprocess) and asserts the captured intermediate artifacts match the
committed snapshots in tests/golden/:

  - tokens.txt       the post-comment/import token stream
  - messages.txt     the constructed Message objects
  - proto/*.proto    every emitted proto (message + service)
  - json/*.h         every emitted JSON adapter (Stage 9)
  - zmq/*.h          every emitted ZMQ transport (Stage 13 zmq)
  - sidecars/        the SQL stub + access/modifier flag files per message

To (re)generate the golden snapshots after an intentional change:

    HARPIA_UPDATE_GOLDEN=1 pytest tests/test_golden.py

Review the resulting diff before committing -- that review IS the point of the
snapshot.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
GOLDEN_DIR = os.path.join(HERE, "golden")
RUNNER = os.path.join(HERE, "run_pipeline.py")
UPDATE = os.environ.get("HARPIA_UPDATE_GOLDEN") == "1"


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    """Run the pipeline once and return the directory of captured artifacts."""
    out = tmp_path_factory.mktemp("harpia_artifacts")
    result = subprocess.run(
        [sys.executable, RUNNER, str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "pipeline runner failed:\n" + result.stdout + result.stderr
    )
    return str(out)


def _relpaths(root):
    """All file paths under root, relative to root, sorted."""
    found = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            full = os.path.join(dirpath, n)
            found.append(os.path.relpath(full, root))
    return sorted(found)


def _check(produced_path, golden_rel):
    """Compare one produced file against its golden, or write it in update mode."""
    golden_path = os.path.join(GOLDEN_DIR, golden_rel)
    with open(produced_path, "r") as f:
        produced = f.read()

    if UPDATE:
        os.makedirs(os.path.dirname(golden_path), exist_ok=True)
        with open(golden_path, "w") as f:
            f.write(produced)
        return

    assert os.path.exists(golden_path), (
        "missing golden file {} -- regenerate with "
        "HARPIA_UPDATE_GOLDEN=1 pytest".format(golden_rel)
    )
    with open(golden_path, "r") as f:
        expected = f.read()
    assert produced == expected, "drift in {}".format(golden_rel)


def test_tokens(artifacts):
    _check(os.path.join(artifacts, "tokens.txt"), "tokens.txt")


def test_messages(artifacts):
    _check(os.path.join(artifacts, "messages.txt"), "messages.txt")


def test_proto_files(artifacts):
    produced_proto_dir = os.path.join(artifacts, "proto")
    produced = _relpaths(produced_proto_dir)

    if UPDATE:
        # Mirror the produced set exactly so deleted protos disappear too.
        golden_proto_dir = os.path.join(GOLDEN_DIR, "proto")
        if os.path.exists(golden_proto_dir):
            shutil.rmtree(golden_proto_dir)
        for rel in produced:
            _check(os.path.join(produced_proto_dir, rel), os.path.join("proto", rel))
        return

    expected = _relpaths(os.path.join(GOLDEN_DIR, "proto"))
    assert produced == expected, "set of generated .proto files changed"
    for rel in produced:
        _check(os.path.join(produced_proto_dir, rel), os.path.join("proto", rel))


def test_json_adapters(artifacts):
    produced_json_dir = os.path.join(artifacts, "json")
    produced = _relpaths(produced_json_dir)

    if UPDATE:
        golden_json_dir = os.path.join(GOLDEN_DIR, "json")
        if os.path.exists(golden_json_dir):
            shutil.rmtree(golden_json_dir)
        for rel in produced:
            _check(os.path.join(produced_json_dir, rel), os.path.join("json", rel))
        return

    expected = _relpaths(os.path.join(GOLDEN_DIR, "json"))
    assert produced == expected, "set of generated JSON adapters changed"
    for rel in produced:
        _check(os.path.join(produced_json_dir, rel), os.path.join("json", rel))


def test_zmq_adapters(artifacts):
    produced_zmq_dir = os.path.join(artifacts, "zmq")
    produced = _relpaths(produced_zmq_dir)

    if UPDATE:
        golden_zmq_dir = os.path.join(GOLDEN_DIR, "zmq")
        if os.path.exists(golden_zmq_dir):
            shutil.rmtree(golden_zmq_dir)
        for rel in produced:
            _check(os.path.join(produced_zmq_dir, rel), os.path.join("zmq", rel))
        return

    expected = _relpaths(os.path.join(GOLDEN_DIR, "zmq"))
    assert produced == expected, "set of generated ZMQ transports changed"
    for rel in produced:
        _check(os.path.join(produced_zmq_dir, rel), os.path.join("zmq", rel))


def test_sidecars(artifacts):
    produced_dir = os.path.join(artifacts, "sidecars")
    produced = _relpaths(produced_dir)

    if UPDATE:
        golden_dir = os.path.join(GOLDEN_DIR, "sidecars")
        if os.path.exists(golden_dir):
            shutil.rmtree(golden_dir)
        for rel in produced:
            _check(os.path.join(produced_dir, rel), os.path.join("sidecars", rel))
        return

    expected = _relpaths(os.path.join(GOLDEN_DIR, "sidecars"))
    assert produced == expected, "set of generated sidecar files changed"
    for rel in produced:
        _check(os.path.join(produced_dir, rel), os.path.join("sidecars", rel))
