"""Session J.21 (Initiatives/multi-language-targets/thread-1-java-target/
histories/Generated-tests-packaging/JUnit-test-generation.md) -- JUnit 5
test generation for the Java target.

One JUnit 5 test class per table-bearing message (field access, JSON/XML
round trip, DB CRUDL round trip) -- a scoped subset of TestAdapter.py's
~8 C++ body builders, matching exactly the columns JavaDatabase's CRUDL
DAO handles. See JavaTestAdapter/CLAUDE.md for what's deliberately not
ported (access-rights/modifiers, live REST/SOAP, the app-level suite).

  - Structural (pure Python, always run): a test class is generated per
    table-bearing message, with all four @Test methods present.
  - Integration (gradle+JDK-gated): `gradle test` actually runs the
    generated suite (JUnit 5 wired via useJUnitPlatform()) and every test
    passes -- this session's own acceptance bar, per its history file
    ("verified together with J.23, not duplicated here" -- this file IS
    that verification, landing now since both prerequisites already
    exist).
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, SKIP_REASON  # noqa: E402

_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None


# -- structural ---------------------------------------------------------

def test_junit_test_class_generated_for_users(tmp_path):
    out = generate(tmp_path, lang="java")
    path = os.path.join(out, "java", "src", "test", "java", "com", "harpia",
                        "generated", "test", "users_Test.java")
    assert os.path.isfile(path)
    text = open(path).read()
    for method in ("fieldsSurviveSetterGetter", "jsonRoundTrip",
                   "xmlRoundTrip", "dbCrudlRoundTrip"):
        assert method in text
    assert 'PK_FIELD = "ID_{}"'.format(HASH) in text


def test_junit_uses_reflection_not_typed_accessors(tmp_path):
    # The whole point of generating via reflection (JavaTestAdapter/
    # CLAUDE.md) is that this file must compile without ever guessing a
    # camelCase accessor name -- spot-check that the setter/getter calls
    # are all through Descriptor/FieldDescriptor, not e.g. "setAddress(".
    out = generate(tmp_path, lang="java")
    path = os.path.join(out, "java", "src", "test", "java", "com", "harpia",
                        "generated", "test", "users_Test.java")
    text = open(path).read()
    assert "findFieldByName" in text
    assert "b.setField(" in text
    assert "setAddress(" not in text and "setName(" not in text


# -- integration: a real gradle+JDK build, actually running the tests ------

@pytest.mark.skipif(not _HAS_JAVA_TOOLCHAIN, reason=SKIP_REASON)
def test_generated_junit_suite_passes(tmp_path):
    out = generate(tmp_path, lang="java")
    java_root = os.path.join(out, "java")

    result = subprocess.run(["gradle", "test"], cwd=java_root,
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, "gradle test failed:\n" + result.stdout + result.stderr

    # Sanity: the test report exists and covers more than zero classes --
    # a green `gradle test` with nothing actually collected would be a
    # false pass (e.g. if useJUnitPlatform() were missing).
    report_dir = os.path.join(java_root, "build", "test-results", "test")
    assert os.path.isdir(report_dir), "no test-results dir -- did any test class run?"
    xml_reports = [f for f in os.listdir(report_dir) if f.endswith(".xml")]
    assert len(xml_reports) >= 10, "expected a report per table-bearing message, got {}".format(
        len(xml_reports))
