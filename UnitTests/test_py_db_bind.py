"""The Python target's DB-API bind/extract runtime (python-target /
py-database task 1, ``harpia_runtime.db.bind``) and the dialect placeholder
(``DbBackend.param_placeholder``).

Pure Python: ``sqlite`` → ``?``, ``postgresql`` → ``%s``.
Image-gated (python protobuf + protoc): for every scalar kind and an enum
found in the fixture, a value bound with ``bind_value`` round-trips through
an in-memory ``sqlite3`` column back via ``extract_value``; ``NULL`` reads
as the default; a message/repeated field is refused.
"""
import os
import sqlite3
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Database.backends import get_backend  # noqa: E402
from UnitTests import _py_cpp_parity as P  # noqa: E402


def test_placeholder_per_backend():
    assert get_backend("sqlite").param_placeholder() == "?"
    assert get_backend("postgresql").param_placeholder() == "%s"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    if not P.HAVE_PY:
        pytest.skip(P.SKIP_PY)
    gen = P.generate_python(tmp_path_factory.mktemp("py_bind"))
    msgs = P.fixture_messages(P.py_root(gen))
    import importlib
    return importlib.import_module("harpia_runtime.db.bind"), msgs


_PROBE = """syntax = "proto3";
package bindprobe;
enum Color { RED = 0; GREEN = 1; BLUE = 2; }
message Kinds {
  int32 i32 = 1; int64 i64 = 2; uint32 u32 = 3; uint64 u64 = 4;
  double d = 5; float f = 6; bool b = 7; string s = 8; Color e = 9;
  optional int32 oi = 10; Kinds child = 11; repeated int32 many = 12;
}
"""


@pytest.fixture(scope="module")
def kinds(env, tmp_path_factory):
    """Every scalar kind + an enum (the HarpiaTest fixture has no bool/int64:
    the DSL has no bool), compiled by the same protoc the generator uses."""
    import importlib
    import subprocess
    d = tmp_path_factory.mktemp("bindprobe")
    (d / "bindprobe.proto").write_text(_PROBE)
    subprocess.run(["protoc", "-I", str(d), "--python_out", str(d),
                    str(d / "bindprobe.proto")], check=True)
    sys.path.insert(0, str(d))
    return importlib.import_module("bindprobe_pb2").Kinds


SAMPLE = {"i32": -123456, "i64": 9007199254740993, "u32": 4000000000,
          "u64": 9000000000000000000, "d": 2.5, "f": 1.25, "b": True,
          "s": "h\u00e9llo 'q'", "e": 2, "oi": 0}


def test_every_kind_round_trips(env, kinds):
    bind, _ = env
    conn = sqlite3.connect(":memory:")
    for name, value in SAMPLE.items():
        m = kinds()
        setattr(m, name, value)
        conn.execute("DROP TABLE IF EXISTS t")
        conn.execute("CREATE TABLE t (v)")
        conn.execute("INSERT INTO t (v) VALUES (?)", (bind.bind_value(m, name),))
        (row,) = conn.execute("SELECT v FROM t").fetchone()
        back = kinds()
        bind.extract_value(row, back, name)
        assert getattr(back, name) == value, name
        if name == "oi":
            assert back.HasField("oi")  # explicitly set, even to 0
        bind.extract_value(None, back, name)
        assert getattr(back, name) == m.DESCRIPTOR.fields_by_name[name].default_value


def test_enum_and_bool_bind_as_int(env, kinds):
    bind, _ = env
    m = kinds(e=2, b=True)
    assert bind.bind_value(m, "e") == 2 and type(bind.bind_value(m, "e")) is int
    assert bind.bind_value(m, "b") == 1 and type(bind.bind_value(m, "b")) is int


def test_fixture_fields_round_trip(env):
    """Every scalar/enum field of every fixture message, with the parity
    harness's deterministic values."""
    bind, msgs = env
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (v)")
    for cls in msgs.values():
        full = P.populate(cls())
        for f in cls.DESCRIPTOR.fields:
            if f.label == f.LABEL_REPEATED or f.cpp_type == f.CPPTYPE_MESSAGE:
                continue
            conn.execute("DELETE FROM t")
            conn.execute("INSERT INTO t (v) VALUES (?)", (bind.bind_value(full, f.name),))
            (row,) = conn.execute("SELECT v FROM t").fetchone()
            back = cls()
            bind.extract_value(row, back, f.name)
            assert getattr(back, f.name) == getattr(full, f.name), f.full_name


def test_non_scalar_refused(env, kinds):
    bind, _ = env
    for name in ("child", "many"):
        with pytest.raises(TypeError):
            bind.bind_value(kinds(), name)
