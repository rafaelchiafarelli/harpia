"""Golden-file regression test for the Java target (session J.23:
initiatives/multi-language-targets/thread-1-java-target/histories/
Generated-tests-packaging/full-generate-build-run-demo-golden-baseline.md
-- "establishes its own golden-snapshot baseline, first of its kind for
this target").

Mirrors tests/test_golden.py's own pattern (same UPDATE/_relpaths/_check
shape) but snapshots the WHOLE <dest>/java/ tree in one comparison rather
than splitting per-adapter subdirectory the way the C++ golden test does
-- the Java target's output is one coherent tree (a single Gradle
project), not C++'s dozen separately-rooted output directories, so one
comprehensive comparison is the natural granularity here.

To (re)generate after an intentional change:

    HARPIA_UPDATE_GOLDEN=1 pytest tests/test_golden_java.py

Review the resulting diff before committing -- that review IS the point.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
GOLDEN_DIR = os.path.join(HERE, "golden_java")
UPDATE = os.environ.get("HARPIA_UPDATE_GOLDEN") == "1"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests._java_gradle_helpers import generate  # noqa: E402


@pytest.fixture(scope="module")
def java_tree(tmp_path_factory):
    out = generate(tmp_path_factory.mktemp("harpia_java_golden"), lang="java")
    return os.path.join(out, "java")


def _relpaths(root):
    found = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            full = os.path.join(dirpath, n)
            found.append(os.path.relpath(full, root))
    return sorted(found)


def test_java_tree_matches_golden(java_tree):
    produced = _relpaths(java_tree)

    if UPDATE:
        if os.path.exists(GOLDEN_DIR):
            shutil.rmtree(GOLDEN_DIR)
        for rel in produced:
            src = os.path.join(java_tree, rel)
            dst = os.path.join(GOLDEN_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        return

    expected = _relpaths(GOLDEN_DIR)
    assert produced == expected, (
        "set of files under the generated java/ tree changed -- "
        "regenerate with HARPIA_UPDATE_GOLDEN=1 pytest tests/test_golden_java.py "
        "and review the diff")

    for rel in produced:
        produced_path = os.path.join(java_tree, rel)
        golden_path = os.path.join(GOLDEN_DIR, rel)
        with open(produced_path, "r") as f:
            got = f.read()
        with open(golden_path, "r") as f:
            want = f.read()
        assert got == want, "drift in java/{}".format(rel)


def test_java_tree_is_write_if_different(tmp_path):
    """Regenerating twice into the same dir doesn't touch unchanged files'
    mtimes -- the same write-if-different contract every C++ adapter
    already honors (Util.util.write_if_different/copy_if_different)."""
    out = generate(tmp_path, lang="java")
    build_gradle = os.path.join(out, "java", "build.gradle")
    mtime1 = os.path.getmtime(build_gradle)
    generate(tmp_path, lang="java")
    mtime2 = os.path.getmtime(build_gradle)
    assert mtime1 == mtime2
