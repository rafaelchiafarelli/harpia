"""The Python target's XML runtime (python-target / py-serialization task 2,
``harpia_runtime.xml``), a port of ``XmlAdapter/runtime/harpia_xml.h``.

Unit (image-gated: python protobuf + protoc): root element = type name,
escaping, ``%f`` floats, proto3 scalars always emitted, presence-gated
``optional``/message fields, nested + repeated + map + enum round trips,
``from_xml`` merges and returns False on a malformed document, C-style
number parsing.

C++ parity (+ g++): for every fixture message, populated, empty, and
populated-then-cleared-of-optionals, ``to_xml`` is byte-identical to the C++
runtime and ``from_xml`` of the C++ output equals the original; the C++
reader parses Python's output back to the original; ``xsd()`` matches C++
for every message type.
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

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("py_xml"))


@pytest.fixture(scope="module")
def env(gen):
    msgs = P.fixture_messages(P.py_root(gen))
    return importlib.import_module("harpia_runtime.xml"), msgs


def _variants(msgs):
    """name -> list of messages: populated, empty, and sparse (only the
    first field set, so presence gating shows)."""
    out = {}
    for name, cls in sorted(msgs.items()):
        full = P.populate(cls())
        sparse = cls()
        first = cls.DESCRIPTOR.fields[0] if cls.DESCRIPTOR.fields else None
        if first is not None and first.label != first.LABEL_REPEATED \
                and first.cpp_type != first.CPPTYPE_MESSAGE:
            setattr(sparse, first.name, getattr(full, first.name))
        out[name] = [full, cls(), sparse]
    return out


def test_shape_and_escaping(env):
    x, msgs = env
    u = msgs["users"](name='a<b>&"c\'', address="x")
    s = x.to_xml(u)
    assert s.startswith("<users>") and s.endswith("</users>")
    assert "<name>a&lt;b&gt;&amp;&quot;c&apos;</name>" in s
    # proto3 implicit-presence scalars are always emitted, even at default
    assert "<STATUS_" in s
    back = msgs["users"]()
    assert x.from_xml(s, back) and back == u


def test_optional_presence(env):
    x, msgs = env
    pv = msgs["patient_vitals"]()
    assert "<device_note>" not in x.to_xml(pv)
    pv.device_note = ""
    assert "<device_note></device_note>" in x.to_xml(pv)
    back = msgs["patient_vitals"]()
    assert x.from_xml(x.to_xml(pv), back) and back.HasField("device_note")


def test_floats_print_like_std_to_string(env):
    x, msgs = env
    for cls in msgs.values():
        for f in cls.DESCRIPTOR.fields:
            if f.cpp_type == f.CPPTYPE_FLOAT and f.label != f.LABEL_REPEATED:
                m = cls()
                setattr(m, f.name, 0.1)
                # float32(0.1) widened to double, printed with %f
                assert "<{0}>0.100000</{0}>".format(f.name) in x.to_xml(m)
                return
    pytest.skip("no float field in the fixture")


def test_from_xml_merges_and_rejects_garbage(env):
    x, msgs = env
    m = msgs["users"](address="kept")
    assert x.from_xml("<users><name>n</name><bogus>1</bogus></users>", m)
    assert m.name == "n" and m.address == "kept"
    assert not x.from_xml("<users><name>", m)


def test_c_style_number_parsing(env):
    import harpia_runtime.reflect as r
    assert r.to_ll("12abc") == 12 and r.to_ll("x") == 0 and r.to_ll(None) == 0
    assert r.to_ll(" -7") == -7 and r.to_ll("99999999999999999999") == 2**63 - 1
    assert r.to_ull("-1") == 2**64 - 1
    assert r.to_d("1.5e3xyz") == 1500.0 and r.to_d(".5") == 0.5 and r.to_d("q") == 0.0


def test_map_round_trip(env):
    x, msgs = env
    for cls in msgs.values():
        for f in cls.DESCRIPTOR.fields:
            if f.message_type is not None and f.message_type.GetOptions().map_entry:
                m = P.populate(cls())
                back = cls()
                assert x.from_xml(x.to_xml(m), back) and back == m
                return
    pytest.skip("no map field in the fixture")


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_to_xml_byte_identical_to_cpp(gen, env):
    x, msgs = env
    cases = [(n, m) for n, vs in _variants(msgs).items() for m in vs]
    res = P.run(gen, [("to_xml", n, m.SerializeToString()) for n, m in cases])
    for (name, m), (ok, out) in zip(cases, res):
        assert ok, name
        assert out.decode() == x.to_xml(m), name
        back = msgs[name]()
        assert x.from_xml(out.decode(), back) and back == m, name


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_cpp_reads_python_xml(gen, env):
    x, msgs = env
    cases = [(n, vs[0]) for n, vs in _variants(msgs).items()]
    res = P.run(gen, [("from_xml", n, x.to_xml(m).encode()) for n, m in cases])
    for (name, m), (ok, out) in zip(cases, res):
        assert ok and msgs[name].FromString(out) == m, name


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_xsd_matches_cpp(gen, env):
    x, msgs = env
    names = sorted(msgs)
    res = P.run(gen, [("xsd", n, None) for n in names])
    for name, (ok, out) in zip(names, res):
        assert ok and out.decode() == x.xsd(msgs[name].DESCRIPTOR), name
