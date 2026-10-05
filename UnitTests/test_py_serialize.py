"""The Python target's ``to_string`` façade + ``phi`` redaction (python-target
/ py-serialization task 4): ``harpia_runtime.serialize``, ``redaction``,
``redaction_audit`` and the generated ``harpia_generated.serialize.phi_registry``.

Unit (image-gated: python protobuf + protoc): the registry lists the schema's
8 phi pairs; ``lab_result`` (all-phi) prints ``[REDACTED]`` for every phi
field in all three formats with no value leaking; ``patient_vitals`` redacts
only its phi fields; a phi-free message is byte-identical to the engines;
the toggle; ``allow_phi_print`` / ``restore_phi_redaction`` record exactly
one entry each, no value in any argument; redacted text is lossy.

C++ parity (+ g++): for every fixture message, ``to_string`` in all three
formats is byte-identical to C++ ``harpia::serialize::to_string``, with
redaction on and off.
"""
import importlib
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests.test_py_xml import _variants  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

SECRET = "SECRET-7731"
_HIDDEN = ("ID_", "STATUS_", "ERROR_", "ORIGINATOR")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("py_ser"))


@pytest.fixture(scope="module")
def env(gen):
    msgs = P.fixture_messages(P.py_root(gen))
    ser = importlib.import_module("harpia_runtime.serialize")
    red = importlib.import_module("harpia_runtime.redaction")
    aud = importlib.import_module("harpia_runtime.redaction_audit")
    reg = importlib.import_module("harpia_generated.serialize.phi_registry")
    yield ser, red, aud, reg, msgs
    red.set_redaction_enabled(True)


def _lab(msgs):
    m = msgs["lab_result"]()
    for f in m.DESCRIPTOR.fields:
        if f.name.startswith(_HIDDEN):
            continue  # harpia's own bookkeeping fields, not phi
        if f.cpp_type == f.CPPTYPE_STRING:
            setattr(m, f.name, SECRET)
        elif f.cpp_type == f.CPPTYPE_INT32:
            setattr(m, f.name, 7731)
        elif f.cpp_type in (f.CPPTYPE_FLOAT, f.CPPTYPE_DOUBLE):
            setattr(m, f.name, 77.31)
    return m


def test_registry(env):
    _, _, _, reg, _ = env
    assert len(reg.PHI_FIELDS) == 8
    assert reg.is_phi("lab_result", "subject_ref")
    assert not reg.is_phi("users", "name")
    assert reg.message_has_phi("patient_vitals") and not reg.message_has_phi("users")


@pytest.mark.parametrize("fmt", ["JSON", "XML", "YAML"])
def test_all_phi_message_redacted(env, fmt):
    ser, red, _, reg, msgs = env
    red.set_redaction_enabled(True)
    text = ser.to_string(_lab(msgs), ser.Format[fmt])
    assert SECRET not in text and "7731" not in text and "77.31" not in text
    phi = [f for m, f in reg.PHI_FIELDS if m == "lab_result"]
    assert text.count(red.PLACEHOLDER) == len(phi)
    for name in phi:
        assert name in text


def test_mixed_message_redacts_only_phi(env):
    ser, red, _, _, msgs = env
    red.set_redaction_enabled(True)
    pv = msgs["patient_vitals"](patient_id=SECRET, device_note="note-ok")
    text = ser.to_string(pv, ser.Format.JSON)
    assert SECRET not in text and "note-ok" in text
    assert '"patient_id":"[REDACTED]"' in text


def test_phi_free_is_byte_identical_to_engines(env):
    ser, red, _, _, msgs = env
    js, xml, yaml = (importlib.import_module("harpia_runtime." + n)
                     for n in ("json", "xml", "yaml"))
    m = P.populate(msgs["shipment"]())
    assert ser.to_string(m, ser.Format.JSON) == js.to_json(m)
    assert ser.to_string(m, ser.Format.XML) == xml.to_xml(m)
    assert ser.to_string(m, ser.Format.YAML) == yaml.to_yaml(m)
    assert ser.format_name(ser.Format.YAML) == "yaml"


def test_toggle_and_audited_opt_out(env):
    ser, red, aud, _, msgs = env
    events = []
    sink_mod = importlib.import_module("harpia_runtime.compliance.audit_sink")

    class Rec(sink_mod.AuditSink):
        def record(self, operation, subject, detail=""):
            events.append((operation, subject, detail))

    lab = _lab(msgs)
    aud.allow_phi_print(Rec(), reason="incident 42")
    try:
        assert not red.redaction_enabled()
        assert SECRET in ser.to_string(lab, ser.Format.XML)
        assert events == [("phi_unredacted_output_enabled", "serialize.redaction",
                           "incident 42")]
    finally:
        aud.restore_phi_redaction(Rec())
    assert red.redaction_enabled()
    assert events[-1] == ("phi_unredacted_output_disabled", "serialize.redaction", "")
    assert len(events) == 2
    assert all(SECRET not in " ".join(e) for e in events)


def test_redacted_text_is_lossy(env):
    ser, red, _, _, msgs = env
    red.set_redaction_enabled(True)
    lab = _lab(msgs)
    assert not ser.from_string(ser.to_string(lab, ser.Format.JSON),
                               msgs["lab_result"](), ser.Format.JSON)
    for fmt in (ser.Format.XML, ser.Format.YAML):
        back = msgs["lab_result"]()
        assert ser.from_string(ser.to_string(lab, fmt), back, fmt)
        for f in back.DESCRIPTOR.fields:
            if f.name.startswith(_HIDDEN):
                continue
            # numeric phi fields fall back to their default; a string phi
            # field reads the placeholder text itself (same as C++)
            want = red.PLACEHOLDER if f.cpp_type == f.CPPTYPE_STRING else 0
            assert getattr(back, f.name) == want, (fmt, f.name)


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
@pytest.mark.parametrize("redact", [True, False])
def test_to_string_byte_identical_to_cpp(gen, env, redact):
    ser, red, _, _, msgs = env
    red.set_redaction_enabled(redact)
    try:
        cases = [(n, m) for n, vs in _variants(msgs).items() for m in vs]
        cases.append(("lab_result", _lab(msgs)))
        reqs = [] if redact else [("redact_off", None, None)]
        for op in ("ser_json", "ser_xml", "ser_yaml"):
            reqs += [(op, n, m.SerializeToString()) for n, m in cases]
        res = P.run(gen, reqs)[0 if redact else 1:]
        fmts = [ser.Format.JSON] * len(cases) + [ser.Format.XML] * len(cases) \
            + [ser.Format.YAML] * len(cases)
        for (name, m), fmt, (ok, out) in zip(cases * 3, fmts, res):
            assert ok, name
            assert out.decode() == ser.to_string(m, fmt), (name, fmt)
    finally:
        red.set_redaction_enabled(True)
