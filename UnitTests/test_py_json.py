"""The Python target's JSON runtime (python-target / py-serialization task 1,
``harpia_runtime.json``).

Unit (image-gated: python protobuf + protoc): compact separators, proto3
defaults omitted, int64 as a string, unknown keys tolerated, a parse failure
returns False and leaves the message untouched, ``is_valid_json`` never
mutates its prototype.

C++ cross-check (+ g++): for every fixture message, populated
deterministically, C++ ``MessageToJsonString`` output parsed by Python equals
the original, and Python ``to_json`` output parsed by the C++ ``from_json``
equals the original; and the bytes are identical too
(``test_json_bytes_identical_to_cpp``).
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("py_json"))


@pytest.fixture(scope="module")
def env(gen):
    root = P.py_root(gen)
    msgs = P.fixture_messages(root)
    import importlib
    return importlib.import_module("harpia_runtime.json"), msgs


def test_runtime_copied(gen):
    assert os.path.isfile(os.path.join(P.py_root(gen), "harpia_runtime", "json.py"))


def test_compact_defaults_omitted_int64_string(env):
    js, msgs = env
    users = msgs["users"](name="ann")
    assert js.to_json(users) == '{"name":"ann"}'
    assert js.to_json(msgs["users"]()) == "{}"
    big = None
    for cls in msgs.values():
        for f in cls.DESCRIPTOR.fields:
            if f.type == f.TYPE_INT64 and f.label != f.LABEL_REPEATED:
                big = (cls, f)
                break
        if big:
            break
    if big:
        cls, f = big
        m = cls()
        setattr(m, f.name, 9007199254740993)
        assert '"9007199254740993"' in js.to_json(m)


def test_camel_case_names(env):
    js, msgs = env
    m = msgs["patient_vitals"](patient_id="p1")
    assert '"patientId":"p1"' in js.to_json(m)


def test_unknown_keys_tolerated_and_failure_untouched(env):
    js, msgs = env
    m = msgs["users"]()
    assert js.from_json('{"name":"x","futureField":3}', m)
    assert m.name == "x"
    assert not js.from_json("not json", m)
    assert not js.from_json('{"name":', m)
    assert m.name == "x"


def test_is_valid_json_does_not_mutate(env):
    js, msgs = env
    proto = msgs["users"](name="keep")
    assert js.is_valid_json('{"name":"other"}', proto)
    assert not js.is_valid_json("[", proto)
    assert proto.name == "keep"


def _populated(msgs):
    return {name: P.populate(cls()) for name, cls in sorted(msgs.items())}


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_cpp_json_parses_in_python(gen, env):
    js, msgs = env
    pop = _populated(msgs)
    res = P.run(gen, [("to_json", n, m.SerializeToString()) for n, m in pop.items()])
    for (name, m), (ok, out) in zip(pop.items(), res):
        assert ok, name
        back = msgs[name]()
        assert js.from_json(out.decode(), back), name
        assert back == m, name


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_python_json_parses_in_cpp(gen, env):
    js, msgs = env
    pop = _populated(msgs)
    res = P.run(gen, [("from_json", n, js.to_json(m).encode()) for n, m in pop.items()])
    for (name, m), (ok, out) in zip(pop.items(), res):
        assert ok, name
        assert msgs[name].FromString(out) == m, name


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_json_bytes_identical_to_cpp(gen, env):
    """Beyond the cross-parse bar: every populated fixture message (stress
    strings included) is byte-identical to C++ MessageToJsonString. Python
    matches C++'s \\u003c / \\u003e escaping of '<' / '>'."""
    js, msgs = env
    pop = _populated(msgs)
    res = P.run(gen, [("to_json", n, m.SerializeToString()) for n, m in pop.items()])
    for (name, m), (ok, out) in zip(pop.items(), res):
        assert ok and out.decode() == js.to_json(m), name
