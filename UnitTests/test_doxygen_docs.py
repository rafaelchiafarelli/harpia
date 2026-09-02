"""Foundation F6 -- Doxygen infrastructure (Doxyfile + CMake `doxygen`
target + the assembled mainpage). Skipped (per-test) when the relevant
tool is absent, same convention as the other toolchain-gated tests.

A scoping note, worth stating explicitly: the plan's own test bullet says
"runs doxygen over a generated project and asserts zero warnings with
WARN_IF_UNDOCUMENTED = YES." Taken completely literally against *today's*
real generated project, that would fail immediately and through no fault
of this task -- none of the existing templates/runtime headers use actual
Doxygen comment syntax yet (`///`/`/** */`), because emitting those is
explicitly Ground Rule 6's job, not F6's ("Out of scope: the per-template
doc-comment content itself"). So instead of asserting zero warnings over
the whole (currently undocumented) generated tree, this file:
  - proves the WARN_IF_UNDOCUMENTED mechanism itself is real and working,
    against a tiny synthetic fixture with one documented and one
    undocumented class (test_warn_if_undocumented_actually_catches_a_gap) --
    this is the part that makes Ground Rule 6 mechanically enforceable
    once later tracks add real doc-comments, and it's fully testable today;
  - proves the actual deliverable (the CMake `doxygen` target, wired
    against the real generated project) builds real HTML docs end to end,
    including the assembled mainpage, without asserting on warning count
    from the current (pre-Ground-Rule-6) generated headers.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_doxygen")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "build")


def test_doxyfile_and_mainpage_are_copied_into_the_generated_project(generated):
    doxyfile = os.path.join(generated, "Doxyfile")
    mainpage = os.path.join(generated, "USAGE_EXCERPT.md")
    assert os.path.isfile(doxyfile)
    assert os.path.isfile(mainpage)

    with open(doxyfile) as f:
        doxyfile_text = f.read()
    assert "USE_MDFILE_AS_MAINPAGE = USAGE_EXCERPT.md" in doxyfile_text
    assert "WARN_IF_UNDOCUMENTED   = YES" in doxyfile_text

    with open(mainpage) as f:
        mainpage_text = f.read()
    # Doxygen/mainpage.py DEFAULT_SECTIONS is (5, 7, 16) since the V1 USAGE.md rewrite.
    assert "## 5. What gets generated" in mainpage_text
    assert "## 7. Consuming the generated code from your own app" in mainpage_text
    assert "## 16. Notes & limits" in mainpage_text


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="doxygen not available")
def test_warn_if_undocumented_actually_catches_a_gap(tmp_path):
    """The mechanism Ground Rule 6 will be held to: a properly Doxygen-
    documented class produces no undocumented-warning; a plain, undocumented
    one does. Same WARN_IF_UNDOCUMENTED=YES/EXTRACT_ALL=NO settings as
    Assets/Doxyfile, against a tiny synthetic source tree -- not the real
    generated project, which isn't Ground-Rule-6-compliant yet."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "clean.h").write_text('''
/// A properly documented class -- must not warn.
class Clean {
public:
    /// Does something.
    void do_something();
};
''')
    (src_dir / "gap.h").write_text('''
class Gap {
public:
    void do_something();
};
''')

    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text('''
PROJECT_NAME = "warn-if-undocumented probe"
OUTPUT_DIRECTORY = {out}
INPUT = {src}
RECURSIVE = YES
FILE_PATTERNS = *.h
GENERATE_HTML = NO
GENERATE_LATEX = NO
EXTRACT_ALL = NO
WARN_IF_UNDOCUMENTED = YES
QUIET = YES
'''.format(out=tmp_path / "out", src=src_dir))

    r = subprocess.run(["doxygen", str(doxyfile)], cwd=str(tmp_path),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, "doxygen failed:\n" + r.stdout + r.stderr

    warnings = r.stderr
    assert "Compound Gap is not documented" in warnings, (
        "expected a warning about the undocumented class:\n" + warnings)
    assert "Clean" not in warnings, (
        "the properly documented class must not warn:\n" + warnings)


@pytest.mark.skipif(
    shutil.which("cmake") is None or shutil.which("doxygen") is None
    or shutil.which("protoc") is None,
    reason="doxygen CMake target proof needs cmake + doxygen + protoc (harpia Docker image)")
def test_doxygen_cmake_target_builds_html(generated, tmp_path):
    """Configure the real generated project and build its `doxygen` target
    (Assets/CMakeLists.txt's find_package(Doxygen) + add_custom_target) --
    the actual F6 deliverable, end to end. Doesn't assert on warning count
    (see the module docstring); asserts the target builds and the mainpage
    reaches the rendered HTML."""
    build = str(tmp_path / "doxygen_build")
    cfg = subprocess.run(["cmake", "-S", generated, "-B", build],
                         capture_output=True, text=True, timeout=300)
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stdout + cfg.stderr

    b = subprocess.run(["cmake", "--build", build, "--target", "doxygen"],
                       capture_output=True, text=True, timeout=300)
    assert b.returncode == 0, "building the doxygen target failed:\n" + b.stdout + b.stderr

    index_html = os.path.join(generated, "docs", "doxygen", "html", "index.html")
    assert os.path.isfile(index_html), "expected {} after building the doxygen target".format(index_html)
    with open(index_html) as f:
        html = f.read()
    assert "What gets generated" in html, (
        "mainpage content should have reached the rendered HTML")
