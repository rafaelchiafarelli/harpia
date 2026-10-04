"""Tests for the `protected` / `open` message-level hardening modifiers
(message-level-hardening initiative, protected-open-modifiers epic, task 1).

`protected` / `open` are message-type-level modifiers, the same shape and slot
as `event`/`stream`/`push`/`pull`/`pushpull`/`critical`/`dds` (before
`message `, trailing space). This task lands them as flags on the AST only
(`Message.is_protected` / `Message.is_open`); the REST/SOAP/gRPC auth-gate
wiring that reads either flag is epic task 3. Neither present -> inherits the
project-wide hardening default, unchanged. Both present on one message is a
hard generation-time error (`CONFLICTING_HARDENING_MODIFIERS`), never a
silent precedence rule.

  - Unit: parse messages with/without `protected`/`open`, alone and combined
    with the transport kinds and `critical`/`dds` (order-independent) and
    with `phi`/`optional`/`repeteable` fields; confirm the AST flags
    `Message.is_protected`/`Message.is_open`; confirm `protected` + `open`
    together is a hard `CONFLICTING_HARDENING_MODIFIERS` error.
  - Integration: Stages 0-6 on a .harpia file with a `protected`/`open`
    message produce a .proto that is line-for-line identical (user fields) to
    the same message without the modifier -- it is a routing flag, it never
    touches the wire format, the same guarantee `phi`/`critical`/`dds` hold.
  - Acceptance gate: existing snapshot tests for messages using neither
    modifier are unchanged -- covered by UnitTests/test_golden.py and
    test_frontend.py.
"""
import json
import os
import re
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


def _protected_map(result):
    return {m["name"]: m["is_protected"] for m in result["messages"]}


def _open_map(result):
    return {m["name"]: m["is_open"] for m in result["messages"]}


def _phi_map(result):
    return {f["field"]: f["is_phi"] for f in result["fields"]}


# -- unit: AST flags --------------------------------------------------------

def test_message_without_modifier_is_not_flagged(tmp_path):
    result = _run(tmp_path, "message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _protected_map(result)["m"] is False
    assert _open_map(result)["m"] is False


def test_message_with_protected_is_flagged(tmp_path):
    result = _run(tmp_path, "protected message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _protected_map(result)["m"] is True
    assert _open_map(result)["m"] is False


def test_message_with_open_is_flagged(tmp_path):
    result = _run(tmp_path, "open message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _open_map(result)["m"] is True
    assert _protected_map(result)["m"] is False


def test_protected_composes_with_each_transport_kind(tmp_path):
    for kind in ("event", "stream", "push", "pull", "pushpull"):
        result = _run(tmp_path, "protected {} message m {{\nint a;\n}};\n".format(kind))
        assert result["error"] is None
        assert _protected_map(result)["m"] is True


def test_open_composes_with_each_transport_kind(tmp_path):
    for kind in ("event", "stream", "push", "pull", "pushpull"):
        result = _run(tmp_path, "open {} message m {{\nint a;\n}};\n".format(kind))
        assert result["error"] is None
        assert _open_map(result)["m"] is True


def test_protected_composes_with_critical_and_dds(tmp_path):
    result = _run(tmp_path, "critical dds protected message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _protected_map(result)["m"] is True


def test_open_composes_with_critical_and_dds(tmp_path):
    result = _run(tmp_path, "critical dds open message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _open_map(result)["m"] is True


def test_modifier_order_does_not_matter(tmp_path):
    # access_modifiers is a flat token list scanned independently for
    # PROTECTED/OPEN regardless of position relative to the other modifiers.
    result = _run(tmp_path, "event critical dds protected message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _protected_map(result)["m"] is True


def test_protected_is_per_message_not_leaking_to_siblings(tmp_path):
    result = _run(tmp_path, (
        "protected message a {\nint x;\n};\n"
        "message b {\nint y;\n};\n"
    ))
    assert result["error"] is None
    protected = _protected_map(result)
    assert protected["a"] is True
    assert protected["b"] is False


def test_open_is_per_message_not_leaking_to_siblings(tmp_path):
    result = _run(tmp_path, (
        "open message a {\nint x;\n};\n"
        "message b {\nint y;\n};\n"
    ))
    assert result["error"] is None
    op = _open_map(result)
    assert op["a"] is True
    assert op["b"] is False


# -- unit: composes with the field modifiers (phi / optional / repeteable) --

def test_protected_message_carries_phi_field(tmp_path):
    result = _run(tmp_path, (
        "protected message m {\n"
        "phi string patient_ref;\n"
        "float spo2;\n"
        "};\n"
    ))
    assert result["error"] is None
    assert _protected_map(result)["m"] is True
    phi = _phi_map(result)
    assert phi["patient_ref"] is True
    assert phi["spo2"] is False


def test_open_message_carries_optional_and_repeteable_fields(tmp_path):
    result = _run(tmp_path, (
        "open message m {\n"
        "optional string note;\n"
        "repeteable[4] int samples;\n"
        "};\n"
    ))
    assert result["error"] is None
    assert _open_map(result)["m"] is True
    assert {f["field"] for f in result["fields"]} >= {"note", "samples"}


# -- unit: conflict is a hard generation-time error, never a precedence rule

def test_protected_and_open_together_is_a_hard_error(tmp_path):
    result = _run(tmp_path, "protected open message m {\nint a;\n};\n")
    assert result["error"] == "MSG CONFLICTING_HARDENING_MODIFIERS"
    assert result["messages"] == []


def test_protected_and_open_together_errors_regardless_of_order(tmp_path):
    result = _run(tmp_path, "open protected message m {\nint a;\n};\n")
    assert result["error"] == "MSG CONFLICTING_HARDENING_MODIFIERS"


# -- integration: Stages 0-6 produce a clean, unaffected .proto -----------

# md5 suffix on hidden field names (ID_/STATUS_/ERROR_/ORIGINATOR_) is taken
# over the whole source text (Message/CLAUDE.md), which the `protected `/
# `open ` prefix changes -- normalise it away so two protos can be compared
# directly.
_HASH_SUFFIX = re.compile(r"_[0-9a-fA-F]{16,}")


def _normalised(proto):
    return [_HASH_SUFFIX.sub("_H", l.strip())
            for l in proto.splitlines() if l.strip()]


def test_protected_message_emits_clean_proto(tmp_path):
    result = _run(tmp_path, "protected message m {\nint heart_rate;\n};\n")
    assert result["error"] is None
    proto = result["proto"]
    assert "message m {" in proto
    assert "int32 heart_rate = " in proto
    # flag only -- no codegen change; the modifier must not leak into the
    # emitted .proto text.
    assert "protected" not in proto.lower()


def test_open_message_emits_clean_proto(tmp_path):
    result = _run(tmp_path, "open message m {\nint heart_rate;\n};\n")
    assert result["error"] is None
    proto = result["proto"]
    assert "message m {" in proto
    assert "int32 heart_rate = " in proto
    assert "open" not in proto.lower()


def test_protected_and_plain_message_emit_identical_proto(tmp_path):
    plain = _run(tmp_path, "message m {\nint a;\nstring b;\n};\n")
    tagged = _run(tmp_path, "protected message m {\nint a;\nstring b;\n};\n")
    assert plain["error"] is None and tagged["error"] is None
    assert _normalised(tagged["proto"]) == _normalised(plain["proto"])
    assert "int32 a = 2;" in tagged["proto"]
    assert "string b = 3;" in tagged["proto"]


def test_open_and_plain_message_emit_identical_proto(tmp_path):
    plain = _run(tmp_path, "message m {\nint a;\nstring b;\n};\n")
    tagged = _run(tmp_path, "open message m {\nint a;\nstring b;\n};\n")
    assert plain["error"] is None and tagged["error"] is None
    assert _normalised(tagged["proto"]) == _normalised(plain["proto"])


def test_hardening_modifiers_do_not_imply_one_to_many_originator(tmp_path):
    # pull/event/stream set isOneToMany -> the ORIGINATOR hidden field gets an
    # md5-suffixed name (ORIGINATOR_<hash>) instead of the bare `ORIGINATOR`.
    # `protected`/`open` must NOT, on their own, flip isOneToMany.
    plain = _run(tmp_path, "message m {\nint a;\n};\n")
    protected = _run(tmp_path, "protected message m {\nint a;\n};\n")
    open_ = _run(tmp_path, "open message m {\nint a;\n};\n")
    one_to_many = _run(tmp_path, "pull message m {\nint a;\n};\n")
    assert plain["error"] is None and protected["error"] is None and open_["error"] is None
    assert one_to_many["error"] is None
    assert _normalised(protected["proto"]) == _normalised(plain["proto"])
    assert _normalised(open_["proto"]) == _normalised(plain["proto"])
    assert re.search(r"ORIGINATOR_[0-9a-fA-F]{16,}", one_to_many["proto"])
    assert not re.search(r"ORIGINATOR_[0-9a-fA-F]{16,}", protected["proto"])
    assert not re.search(r"ORIGINATOR_[0-9a-fA-F]{16,}", open_["proto"])
