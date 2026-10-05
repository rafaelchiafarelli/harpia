"""The Python target's YAML runtime (python-target / py-serialization task 3,
``harpia_runtime.yaml``), a port of ``YamlAdapter/runtime/harpia_yaml.h``
(not PyYAML).

Unit (image-gated: python protobuf + protoc): flat / nested-repeated / map
round trips, quoting, ``[]``/``{}`` for empties, an empty document ``{}``
parses to an empty message, garbage with no matching key returns False, the
generated ``pyproject.toml`` has no PyYAML dependency.

C++ parity (+ g++): for every fixture message (populated / empty / sparse)
``to_yaml`` is byte-identical to the C++ runtime, ``from_yaml`` of the C++
output equals the original, the C++ reader parses Python's output back to
the original, and ``from_yaml``'s bool return matches C++ everywhere,
including the empty document ``{}`` (cpp-yaml-empty-mapping-DEFECT).
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


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("py_yaml"))


@pytest.fixture(scope="module")
def env(gen):
    msgs = P.fixture_messages(P.py_root(gen))
    return importlib.import_module("harpia_runtime.yaml"), msgs


def test_flat_shape(env):
    y, msgs = env
    s = y.to_yaml(msgs["users"](name='a"b\\c\nd\te', address="x"))
    assert s.startswith("ID_")
    assert 'name: "a\\"b\\\\c\\nd\\te"\n' in s
    back = msgs["users"]()
    assert y.from_yaml(s, back) and back.name == 'a"b\\c\nd\te'


def test_empty_document(env):
    y, msgs = env
    assert y.to_yaml(msgs["shipment"]()).count("cargo: []") == 1
    m = msgs["users"]()
    assert y.from_yaml("{}\n", m) and m == msgs["users"]()


def test_garbage_returns_false(env):
    y, msgs = env
    assert not y.from_yaml("nothing: here\nat: all\n", msgs["users"]())
    assert y.from_yaml("", msgs["users"]())


def test_nested_repeated_and_map_round_trip(env):
    y, msgs = env
    for name in ("shipment", "queen"):
        m = P.populate(msgs[name]())
        back = msgs[name]()
        assert y.from_yaml(y.to_yaml(m), back) and back == m, name


def test_no_pyyaml_dependency(gen):
    text = open(os.path.join(P.py_root(gen), "pyproject.toml")).read().lower()
    assert "pyyaml" not in text


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_to_yaml_byte_identical_to_cpp(gen, env):
    y, msgs = env
    cases = [(n, m) for n, vs in _variants(msgs).items() for m in vs]
    res = P.run(gen, [("to_yaml", n, m.SerializeToString()) for n, m in cases])
    for (name, m), (ok, out) in zip(cases, res):
        assert ok, name
        assert out.decode() == y.to_yaml(m), name
        back = msgs[name]()
        y.from_yaml(out.decode(), back)
        assert back == m, name


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_from_yaml_return_matches_cpp(gen, env):
    y, msgs = env
    cases = [(n, m) for n, vs in _variants(msgs).items() for m in vs]
    texts = [y.to_yaml(m) for _, m in cases]
    res = P.run(gen, [("from_yaml", n, t.encode()) for (n, _), t in zip(cases, texts)])
    for (name, _), text, (ok, _) in zip(cases, texts, res):
        assert y.from_yaml(text, msgs[name]()) == ok, name
    assert "{}\n" in texts  # the empty-document case is really exercised
    # the bare empty document, for every type: both True, nothing merged
    names = sorted(msgs)
    res = P.run(gen, [("from_yaml", n, b"{}") for n in names])
    for name, (ok, out) in zip(names, res):
        fresh = msgs[name]()
        assert ok and y.from_yaml("{}", fresh), name
        assert msgs[name].FromString(out) == msgs[name](), name


@pytest.mark.skipif(not P.HAVE_CPP, reason=P.SKIP_CPP)
def test_cpp_reads_python_yaml(gen, env):
    y, msgs = env
    cases = [(n, vs[0]) for n, vs in _variants(msgs).items()]
    res = P.run(gen, [("from_yaml", n, y.to_yaml(m).encode()) for n, m in cases])
    for (name, m), (_ok, out) in zip(cases, res):
        assert msgs[name].FromString(out) == m, name
