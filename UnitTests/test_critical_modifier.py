"""Tests for the `critical` message-type modifier (Phase 1a of
Initiatives/medical_devices/sensitive-data-implementation-roadmap.md).

The `critical` modifier is the criticality axis of the sensitive-data design
rules (§0) -- message-type-level, independent of any field's `phi`. This phase
lands it as a flag on the AST only; the delivery-guarantee machinery it will
eventually gate (bounded rotating queue / 2-slot mailbox) is Phase 3.

  - Unit: parse messages with/without `critical`, alone and combined with the
    transport kinds (`event`/`stream`/`push`/`pull`), order-independent, and
    together with a `phi` field on the same message (Rule 0: independent axes);
    confirm the AST flag `Message.is_critical`.
  - Integration: Stages 0-6 on a .harpia file with a `critical` message produce
    a clean .proto -- flag only, the modifier itself never leaks into the
    emitted text.
  - Acceptance gate: existing snapshot tests for non-`critical` messages are
    unchanged -- covered by UnitTests/test_golden.py and test_frontend.py.
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


def _critical_map(result):
    return {m["name"]: m["is_critical"] for m in result["messages"]}


# -- unit: AST flag ----------------------------------------------------------

def test_message_without_critical_is_not_flagged(tmp_path):
    result = _run(tmp_path, "message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _critical_map(result)["m"] is False


def test_message_with_critical_is_flagged(tmp_path):
    result = _run(tmp_path, "critical message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _critical_map(result)["m"] is True


def test_critical_composes_with_event(tmp_path):
    # design-rules doc §0's canonical example: `critical event message ...`
    result = _run(tmp_path, "critical event message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _critical_map(result)["m"] is True


def test_critical_composes_with_stream(tmp_path):
    result = _run(tmp_path, "critical stream message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _critical_map(result)["m"] is True


def test_critical_composes_with_push(tmp_path):
    result = _run(tmp_path, "critical push message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _critical_map(result)["m"] is True


def test_critical_composes_with_pull(tmp_path):
    result = _run(tmp_path, "critical pull message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _critical_map(result)["m"] is True


def test_modifier_order_does_not_matter(tmp_path):
    # `critical` before or after the transport kind -- access_modifiers is a
    # flat token list scanned for CRITICAL regardless of position.
    result = _run(tmp_path, "event critical message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _critical_map(result)["m"] is True


def test_critical_and_phi_are_independent_axes(tmp_path):
    # Rule 0: a message can be high-criticality AND high-confidentiality; the
    # two tags are orthogonal and both apply to the same schema.
    result = _run(tmp_path, (
        "critical event message alarm {\n"
        "phi string patient_id;\n"
        "string alarm_type;\n"
        "int severity;\n"
        "};\n"
    ))
    assert result["error"] is None
    assert _critical_map(result)["alarm"] is True
    phi = {f["field"]: f["is_phi"] for f in result["fields"]}
    assert phi["patient_id"] is True
    assert phi["alarm_type"] is False


def test_critical_is_per_message_not_leaking_to_siblings(tmp_path):
    result = _run(tmp_path, (
        "critical message a {\nint x;\n};\n"
        "message b {\nint y;\n};\n"
    ))
    assert result["error"] is None
    crit = _critical_map(result)
    assert crit["a"] is True
    assert crit["b"] is False


# -- integration: Stages 0-6 produce a clean, unaffected .proto -------------

def test_critical_message_emits_clean_proto(tmp_path):
    result = _run(tmp_path, "critical event message m {\nint heart_rate;\n};\n")
    assert result["error"] is None
    proto = result["proto"]
    assert "message m {" in proto
    assert "int32 heart_rate = " in proto
    # flag only -- no codegen change yet; the modifier must not leak into the
    # emitted .proto text.
    assert "critical" not in proto.lower()


def test_critical_and_plain_message_emit_identical_proto_shape(tmp_path):
    # A `critical` message and a plain one with the same body must produce the
    # same field lines. (Hidden ID_/STATUS_/ERROR_ fields are hash-suffixed off
    # the differing source text -- see Message/CLAUDE.md -- so compare only the
    # user field's own line.)
    plain = _run(tmp_path, "message m {\nint a;\n};\n")
    tagged = _run(tmp_path, "critical message m {\nint a;\n};\n")
    assert plain["error"] is None and tagged["error"] is None
    plain_line = next(l for l in plain["proto"].splitlines() if " a = " in l)
    tagged_line = next(l for l in tagged["proto"].splitlines() if " a = " in l)
    assert plain_line == tagged_line == "int32 a = 2;"
