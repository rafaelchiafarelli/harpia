"""Unit tests for Foundation F6's Doxygen/mainpage.py -- assembling the
Doxygen mainpage from slices of USAGE.md.

Pure Python, no toolchain needed. See tests/test_doxygen_docs.py for the
doxygen/cmake-gated tests that exercise the actual Doxyfile + CMake target.
"""
import os

from Doxygen.mainpage import (
    DEFAULT_USAGE_MD,
    MAINPAGE_FILENAME,
    extract_usage_sections,
    write_mainpage,
)

_FAKE_USAGE_MD = """# Using Harpia

## 1. Quick start

quick start text

## 4. What gets generated

section four text
more section four text

## 5. Building the generated project

section five text

## 6. Wiring the generated code into your own project

section six text

## 11. Notes & limits

section eleven text
"""


def _write_fake_usage(tmp_path):
    path = tmp_path / "USAGE.md"
    path.write_text(_FAKE_USAGE_MD, encoding="utf-8")
    return str(path)


def test_default_usage_md_exists():
    assert os.path.isfile(DEFAULT_USAGE_MD)


def test_extracts_requested_sections_only(tmp_path):
    path = _write_fake_usage(tmp_path)
    content = extract_usage_sections(usage_md_path=path, sections=(4, 6, 11))
    assert "## 4. What gets generated" in content
    assert "section four text" in content
    assert "## 6. Wiring the generated code into your own project" in content
    assert "section six text" in content
    assert "## 11. Notes & limits" in content
    assert "section eleven text" in content
    # explicitly NOT requested -- must not leak in
    assert "## 1. Quick start" not in content
    assert "quick start text" not in content
    assert "## 5. Building the generated project" not in content
    assert "section five text" not in content


def test_sections_appear_in_requested_order(tmp_path):
    path = _write_fake_usage(tmp_path)
    content = extract_usage_sections(usage_md_path=path, sections=(11, 4))
    assert content.index("## 11.") < content.index("## 4.")


def test_section_stops_before_next_heading_not_after(tmp_path):
    # section 4's body must not swallow section 5's content.
    path = _write_fake_usage(tmp_path)
    content = extract_usage_sections(usage_md_path=path, sections=(4,))
    assert "more section four text" in content
    assert "section five text" not in content


def test_missing_section_raises(tmp_path):
    path = _write_fake_usage(tmp_path)
    try:
        extract_usage_sections(usage_md_path=path, sections=(99,))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_real_usage_md_default_sections_extract_cleanly():
    # against the actual repo USAGE.md, not the fake fixture above.
    content = extract_usage_sections()
    assert "## 4. What gets generated" in content
    assert "## 6. Wiring the generated code into your own project" in content
    assert "## 11. Notes & limits" in content
    assert "## 5." not in content
    assert "## 12." not in content


def test_write_mainpage_writes_expected_file(tmp_path):
    path = write_mainpage(str(tmp_path), usage_md_path=_write_fake_usage(tmp_path),
                          sections=(4,))
    assert os.path.basename(path) == MAINPAGE_FILENAME
    assert os.path.isfile(path)
    with open(path) as f:
        content = f.read()
    assert "section four text" in content


def test_write_mainpage_is_write_if_different(tmp_path):
    usage_path = _write_fake_usage(tmp_path)
    path = write_mainpage(str(tmp_path), usage_md_path=usage_path, sections=(4,))
    mtime1 = os.stat(path).st_mtime_ns
    write_mainpage(str(tmp_path), usage_md_path=usage_path, sections=(4,))
    mtime2 = os.stat(path).st_mtime_ns
    assert mtime1 == mtime2
