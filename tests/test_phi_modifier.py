"""Tests for Foundation F2 -- the `phi` (sensitive-field) modifier.

Per initiatives/medical_devices/epics/thread-0-foundation/histories/
phi-field-modifier.md:
  - Unit: parse messages with/without `phi`, alone and combined with other
    modifiers; confirm AST flags (`variable.is_phi`).
  - Integration: Stages 0-6 on a .harpia file with `phi` fields produce a
    clean .proto.
  - Acceptance gate: existing snapshot tests for non-`phi` messages are
    unchanged -- covered by tests/test_golden.py and tests/test_frontend.py
    (neither touches a `phi` field, and both still pass unmodified).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_phi_check.py")


def _run(tmp_path, contents):
    src = tmp_path / "case.harpia"
    src.write_text(contents, encoding="utf-8")
    dest = tmp_path / "dest"
    r = subprocess.run(
        [sys.executable, RUNNER, str(src), str(dest)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, "run_phi_check.py crashed:\n" + r.stdout + r.stderr
    lines = [ln[len("PHI_CHECK_RESULT "):] for ln in r.stdout.splitlines()
             if ln.startswith("PHI_CHECK_RESULT ")]
    assert len(lines) == 1, "expected one PHI_CHECK_RESULT line, got:\n" + r.stdout
    return json.loads(lines[0])


def _phi_map(result):
    return {f["field"]: f["is_phi"] for f in result["fields"]}


# -- unit: AST flags -----------------------------------------------------

def test_field_without_phi_is_not_flagged(tmp_path):
    result = _run(tmp_path, "message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _phi_map(result)["a"] is False


def test_field_with_phi_is_flagged(tmp_path):
    result = _run(tmp_path, "message m {\nphi int a;\n};\n")
    assert result["error"] is None
    assert _phi_map(result)["a"] is True


def test_phi_is_per_field_not_whole_message(tmp_path):
    # design-rules doc Rule 0: one message legitimately mixes phi and
    # non-phi fields.
    result = _run(tmp_path, "message m {\nphi int a;\nstring b;\n};\n")
    assert result["error"] is None
    phi = _phi_map(result)
    assert phi["a"] is True
    assert phi["b"] is False


def test_phi_composes_with_optional(tmp_path):
    result = _run(tmp_path, "message m {\nphi optional string a;\n};\n")
    assert result["error"] is None
    assert _phi_map(result)["a"] is True


def test_phi_composes_with_required(tmp_path):
    result = _run(tmp_path, "message m {\nphi required string a;\n};\n")
    assert result["error"] is None
    assert _phi_map(result)["a"] is True


def test_phi_composes_with_unique(tmp_path):
    result = _run(tmp_path, "message m {\nphi unique int a;\n};\n")
    assert result["error"] is None
    assert _phi_map(result)["a"] is True


def test_phi_composes_with_repeteable(tmp_path):
    result = _run(tmp_path, "message m {\nphi repeteable[4] int a;\n};\n")
    assert result["error"] is None
    assert _phi_map(result)["a"] is True


def test_modifier_order_does_not_matter(tmp_path):
    result = _run(tmp_path, "message m {\noptional phi string a;\n};\n")
    assert result["error"] is None
    assert _phi_map(result)["a"] is True


def test_phi_on_composed_type_field(tmp_path):
    result = _run(tmp_path, (
        "message Inner {\nint x;\n};\n"
        "message Outer {\nphi Inner a;\n};\n"
    ))
    assert result["error"] is None
    phi = _phi_map(result)
    assert phi["a"] is True


# -- integration: Stages 0-6 produce a clean, unaffected .proto -----------

def test_phi_field_emits_clean_proto(tmp_path):
    result = _run(tmp_path, "message m {\nphi int heart_rate;\n};\n")
    assert result["error"] is None
    proto = result["proto"]
    assert "message m {" in proto
    assert "int32 heart_rate = " in proto
    # flag only -- no codegen change; the modifier itself must not leak into
    # the emitted .proto text.
    assert "phi" not in proto.lower()


def test_phi_and_non_phi_fields_emit_identical_proto_shape(tmp_path):
    # F2's guarantee: fields without phi behave exactly as before. A phi
    # field and a plain field of the same type must produce the same
    # "<type> <name> = <index>;" shape. (The two fixtures' hidden ID_/
    # STATUS_/ERROR_ fields are hash-suffixed off the differing source text
    # itself -- see message/CLAUDE.md -- so only the "a" field's own line is
    # a fair comparison, not the whole proto.)
    plain = _run(tmp_path, "message m {\nint a;\n};\n")
    tagged = _run(tmp_path, "message m {\nphi int a;\n};\n")
    assert plain["error"] is None and tagged["error"] is None
    plain_line = next(l for l in plain["proto"].splitlines() if " a = " in l)
    tagged_line = next(l for l in tagged["proto"].splitlines() if " a = " in l)
    assert plain_line == tagged_line == "int32 a = 2;"
