"""Golden-file regression test for the Python target (python-target /
py-foundation task 2).

Mirrors test_golden_java.py: one whole-``<dest>/python/``-tree comparison.
protoc's own output (``*_pb2.py``, ``*_pb2.pyi``, ``*_pb2_grpc.py``) is not
snapshotted -- same convention as the C++ golden, which snapshots the
``.proto`` files but never ``.pb.h``/``.pb.cc`` -- so this test runs without
protoc. ``test_python_codegen.py`` covers the compiled modules.

To (re)generate after an intentional change:

    HARPIA_UPDATE_GOLDEN=1 pytest UnitTests/test_golden_python.py

Review the resulting diff before committing -- that review IS the point.
"""
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
GOLDEN_DIR = os.path.join(HERE, "golden_python")
UPDATE = os.environ.get("HARPIA_UPDATE_GOLDEN") == "1"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate  # noqa: E402

_PROTOC_OUTPUT_SUFFIXES = ("_pb2.py", "_pb2.pyi", "_pb2_grpc.py")


def _is_snapshotted(rel):
    return not rel.endswith(_PROTOC_OUTPUT_SUFFIXES) and "__pycache__" not in rel


@pytest.fixture(scope="module")
def python_tree(tmp_path_factory):
    out = generate(tmp_path_factory.mktemp("harpia_python_golden"), lang="python")
    return os.path.join(out, "python")


def _relpaths(root):
    found = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            rel = os.path.relpath(os.path.join(dirpath, n), root)
            if _is_snapshotted(rel):
                found.append(rel)
    return sorted(found)


def test_python_tree_matches_golden(python_tree):
    produced = _relpaths(python_tree)

    if UPDATE:
        if os.path.exists(GOLDEN_DIR):
            shutil.rmtree(GOLDEN_DIR)
        for rel in produced:
            dst = os.path.join(GOLDEN_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(python_tree, rel), dst)
        return

    expected = _relpaths(GOLDEN_DIR)
    assert produced == expected, (
        "set of files under the generated python/ tree changed -- "
        "regenerate with HARPIA_UPDATE_GOLDEN=1 pytest UnitTests/test_golden_python.py "
        "and review the diff")

    for rel in produced:
        with open(os.path.join(python_tree, rel), "rb") as f:
            got = f.read()
        with open(os.path.join(GOLDEN_DIR, rel), "rb") as f:
            want = f.read()
        assert got == want, "drift in python/{}".format(rel)


def test_python_tree_is_write_if_different(tmp_path):
    out = generate(tmp_path, lang="python")
    probes = [os.path.join(out, "python", "pyproject.toml"),
              os.path.join(out, "python", "harpia_runtime", "__init__.py")]
    pb2 = os.path.join(out, "python", "harpia_generated", "protofiles",
                       "errorCode_pb2.py")
    if os.path.exists(pb2):
        probes.append(pb2)
    before = [os.stat(p).st_mtime_ns for p in probes]
    generate(tmp_path, lang="python")
    assert [os.stat(p).st_mtime_ns for p in probes] == before


def test_default_and_java_do_not_create_python_project(tmp_path):
    assert not os.path.exists(os.path.join(generate(tmp_path / "cpp"), "python"))
    assert not os.path.exists(os.path.join(
        generate(tmp_path / "java", lang="java"), "python"))
