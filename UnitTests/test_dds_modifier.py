"""Tests for the `dds` transport-selection modifier (dds-transport epic,
task 1 -- ASTM F2761 / OpenICE-class bedside bus).

`dds` is a message-type-level transport modifier, the same shape and slot as
`event`/`stream`/`push`/`pull`/`pushpull` and `critical` (before `message `,
trailing space). This task lands it as a flag on the AST only
(`Message.is_dds`); the `DdsAdapter/`, QoS mapping and DDS-Security wiring that
read the flag are tasks 2a/2b/3.

  - Unit: parse messages with/without `dds`, alone and combined with the
    transport kinds and `critical` (order-independent) and with `phi` /
    `optional` / `repeteable` fields; confirm the AST flag `Message.is_dds`.
  - Integration: Stages 0-6 on a .harpia file with a `dds` message produce a
    .proto that is line-for-line identical (user fields) to the same message
    without `dds` -- it is a routing flag, it never touches the wire format,
    the same guarantee `phi` / `critical` hold.
  - Acceptance gate: existing snapshot tests for non-`dds` messages are
    unchanged -- covered by UnitTests/test_golden.py and test_frontend.py.
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


def _dds_map(result):
    return {m["name"]: m["is_dds"] for m in result["messages"]}


def _phi_map(result):
    return {f["field"]: f["is_phi"] for f in result["fields"]}


# -- unit: AST flag --------------------------------------------------------

def test_message_without_dds_is_not_flagged(tmp_path):
    result = _run(tmp_path, "message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is False


def test_message_with_dds_is_flagged(tmp_path):
    result = _run(tmp_path, "dds message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_dds_composes_with_event(tmp_path):
    result = _run(tmp_path, "dds event message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_dds_composes_with_stream(tmp_path):
    result = _run(tmp_path, "dds stream message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_dds_composes_with_push(tmp_path):
    result = _run(tmp_path, "dds push message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_dds_composes_with_pull(tmp_path):
    result = _run(tmp_path, "dds pull message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_dds_composes_with_pushpull(tmp_path):
    result = _run(tmp_path, "dds pushpull message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_dds_composes_with_critical(tmp_path):
    # criticality and transport selection are independent axes: a `critical`
    # alarm can also need to reach an ICE-class DDS bus.
    result = _run(tmp_path, "critical dds message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_modifier_order_does_not_matter(tmp_path):
    # `dds` before or after the transport kind / `critical` -- access_modifiers
    # is a flat token list scanned for DDS regardless of position.
    result = _run(tmp_path, "event critical dds message m {\nint a;\n};\n")
    assert result["error"] is None
    assert _dds_map(result)["m"] is True


def test_dds_is_per_message_not_leaking_to_siblings(tmp_path):
    result = _run(tmp_path, (
        "dds message a {\nint x;\n};\n"
        "message b {\nint y;\n};\n"
    ))
    assert result["error"] is None
    dds = _dds_map(result)
    assert dds["a"] is True
    assert dds["b"] is False


# -- unit: composes with the field modifiers (phi / optional / repeteable) --

def test_dds_message_carries_phi_field(tmp_path):
    # the dds-transport epic's phi-over-DDS audit task (task 4) fixture shape:
    # `dds` on the message, `phi` on a field, independent flags.
    result = _run(tmp_path, (
        "dds message m {\n"
        "phi string patient_ref;\n"
        "float spo2;\n"
        "};\n"
    ))
    assert result["error"] is None
    assert _dds_map(result)["m"] is True
    phi = _phi_map(result)
    assert phi["patient_ref"] is True
    assert phi["spo2"] is False


def test_dds_message_carries_optional_and_repeteable_fields(tmp_path):
    result = _run(tmp_path, (
        "dds message m {\n"
        "optional string note;\n"
        "repeteable[4] int samples;\n"
        "};\n"
    ))
    assert result["error"] is None
    assert _dds_map(result)["m"] is True
    assert {f["field"] for f in result["fields"]} >= {"note", "samples"}


# -- integration: Stages 0-6 produce a clean, unaffected .proto -----------

# md5 suffix on hidden field names (ID_/STATUS_/ERROR_/ORIGINATOR_) is taken
# over the whole source text (Message/CLAUDE.md), which the `dds ` prefix
# changes -- normalise it away so two protos can be compared directly.
_HASH_SUFFIX = re.compile(r"_[0-9a-fA-F]{16,}")


def _normalised(proto):
    return [_HASH_SUFFIX.sub("_H", l.strip())
            for l in proto.splitlines() if l.strip()]


def test_dds_message_emits_clean_proto(tmp_path):
    result = _run(tmp_path, "dds message m {\nint heart_rate;\n};\n")
    assert result["error"] is None
    proto = result["proto"]
    assert "message m {" in proto
    assert "int32 heart_rate = " in proto
    # flag only -- no codegen change; the modifier must not leak into the
    # emitted .proto text.
    assert "dds" not in proto.lower()


def test_dds_and_plain_message_emit_identical_proto(tmp_path):
    # `dds` is a routing flag: a `dds` message and a plain one with the same
    # body produce a line-for-line identical .proto (modulo the md5 suffix on
    # hidden field names, which is over the source text).
    plain = _run(tmp_path, "message m {\nint a;\nstring b;\n};\n")
    tagged = _run(tmp_path, "dds message m {\nint a;\nstring b;\n};\n")
    assert plain["error"] is None and tagged["error"] is None
    assert _normalised(tagged["proto"]) == _normalised(plain["proto"])
    assert "int32 a = 2;" in tagged["proto"]
    assert "string b = 3;" in tagged["proto"]


def test_dds_does_not_imply_one_to_many_originator(tmp_path):
    # pull/event/stream set isOneToMany -> the ORIGINATOR hidden field gets an
    # md5-suffixed name (ORIGINATOR_<hash>) instead of the bare `ORIGINATOR`.
    # `dds` must NOT, on its own, flip isOneToMany: a bare `dds` message keeps
    # the plain shape, and only pull/event/stream introduce the suffixed form.
    plain = _run(tmp_path, "message m {\nint a;\n};\n")
    tagged = _run(tmp_path, "dds message m {\nint a;\n};\n")
    one_to_many = _run(tmp_path, "pull message m {\nint a;\n};\n")
    assert plain["error"] is None and tagged["error"] is None
    assert one_to_many["error"] is None
    assert _normalised(tagged["proto"]) == _normalised(plain["proto"])
    assert re.search(r"ORIGINATOR_[0-9a-fA-F]{16,}", one_to_many["proto"])
    assert not re.search(r"ORIGINATOR_[0-9a-fA-F]{16,}", tagged["proto"])
