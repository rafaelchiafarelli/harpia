"""Generated Python schema migrations, child tables (python-target /
py-database task 5b). Uses the fixture's ``telemetry`` (repeated-scalar
``samples`` / ``notes``, maps ``gauges`` / ``flags``, repeated-composed
``traces``; ``notes`` / ``flags`` / ``traces`` carry ``renamed_from``) and
``beacon_log`` (no child tables), starting from hand-built older states the
same way ``test_stage8_db.py`` drives the C++ child-table migration.

Image-gated (python protobuf + protoc), SQLite:
- add: missing child tables are created;
- rename: ``<table>__old_*`` moves to ``<table>__*`` with its rows, readable
  through the Python DAO;
- reap: an undeclared ``<table>__*`` table is dropped, also for a message
  with no child tables left (``beacon_log``);
- evolve: repeated-scalar ``value`` retype, map ``key``/``value`` retype,
  repeated-composed add/drop/retype, rows CAST across;
- every case is idempotent.

g++ + SOCI: from the same starting databases (the hand-built "C++ v1"
states, maps included), the C++ and the Python migrations end in the same
schema, rows and ``_harpia_schema_version`` row.
"""
import importlib
import os
import sqlite3
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
T = "telemetry_table"
ID = "ID_" + HASH

_MAIN = [
    'CREATE TABLE "{t}" ("{id}" INTEGER PRIMARY KEY, "label" TEXT);',
    "INSERT INTO \"{t}\" VALUES (1, 'dev');",
]

# hand-built older states of telemetry_table and its child tables
STARTS = {
    "add": _MAIN,
    "rename": _MAIN + [
        'CREATE TABLE "{t}__old_notes" ("owner" INTEGER, "ordinal" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "ordinal"));',
        "INSERT INTO \"{t}__old_notes\" VALUES (1, 0, 'alpha'), (1, 1, 'beta');",
        'CREATE TABLE "{t}__old_flags" ("owner" INTEGER, "key" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "key"));',
        "INSERT INTO \"{t}__old_flags\" VALUES (1, -3, 'neg'), (1, 4, 'four');",
        'CREATE TABLE "{t}__old_traces" ("owner" INTEGER, "ordinal" INTEGER, '
        '"kind" TEXT, "weight" INTEGER, PRIMARY KEY("owner", "ordinal"));',
        "INSERT INTO \"{t}__old_traces\" VALUES (1, 0, 'spike', 9);",
    ],
    "reap": _MAIN + [
        'CREATE TABLE "{t}__gone" ("owner" INTEGER, "ordinal" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "ordinal"));',
        "INSERT INTO \"{t}__gone\" VALUES (1, 0, 'orphan');",
    ],
    "scalar_retype": _MAIN + [
        'CREATE TABLE "{t}__samples" ("owner" INTEGER, "ordinal" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "ordinal"));',
        "INSERT INTO \"{t}__samples\" VALUES (1, 0, '42'), (1, 1, '7');",
    ],
    "map_retype": _MAIN + [
        'CREATE TABLE "{t}__gauges" ("owner" INTEGER, "key" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "key"));',
        "INSERT INTO \"{t}__gauges\" VALUES (1, 7, '42'), (1, 8, '99');",
    ],
    "composed_retype": _MAIN + [
        'CREATE TABLE "{t}__traces" ("owner" INTEGER, "ordinal" INTEGER, '
        '"kind" INTEGER, "note" TEXT, PRIMARY KEY("owner", "ordinal"));',
        "INSERT INTO \"{t}__traces\" VALUES (1, 0, 5, 'legacy'), (1, 1, 8, 'stale');",
    ],
}

CHILDREN = ("gauges", "flags", "samples", "notes", "traces")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_migrate_children"))
    P.fixture_messages(P.py_root(g))  # puts the generated tree on sys.path
    return g


def _mig(name="telemetry"):
    return importlib.import_module(
        "harpia_generated.migrate.{}_{}_migrate".format(name, HASH))


def _read(conn):
    dao = importlib.import_module("harpia_generated.db.telemetry_{}_dao".format(HASH))
    got = dao.telemetry()
    assert dao.telemetry_dao(conn).read(1, got)
    return got


def _start(path, case):
    conn = sqlite3.connect(str(path))
    for sql in STARTS[case]:
        conn.execute(sql.format(t=T, id=ID))
    conn.commit()
    return conn


def _tables(conn):
    return sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"))


def _state(conn):
    """Every table's columns and rows, plus the version rows."""
    state = {}
    for t in _tables(conn):
        cols = [tuple(r[1:3]) for r in conn.execute('PRAGMA table_info("{}")'.format(t))]
        rows = conn.execute('SELECT * FROM "{}" ORDER BY 1, 2'.format(t)).fetchall()
        state[t] = (cols, rows)
    return state


def _cols(conn, table):
    return dict(tuple(r[1:3]) for r in conn.execute('PRAGMA table_info("{}")'.format(table)))


def _migrate_twice(conn):
    assert _mig().migrate_telemetry(conn)
    first = _state(conn)
    assert _mig().migrate_telemetry(conn)  # idempotent
    assert _state(conn) == first
    return first


def test_add_creates_child_tables(gen, tmp_path):
    conn = _start(tmp_path / "a.sqlite", "add")
    _migrate_twice(conn)
    assert {"{}__{}".format(T, c) for c in CHILDREN} <= set(_tables(conn))
    assert _read(conn).label == "dev"


def test_rename_keeps_child_rows(gen, tmp_path):
    conn = _start(tmp_path / "b.sqlite", "rename")
    _migrate_twice(conn)
    tables = set(_tables(conn))
    assert not {t for t in tables if "__old_" in t}
    got = _read(conn)
    assert list(got.notes) == ["alpha", "beta"]
    assert dict(got.flags) == {-3: "neg", 4: "four"}
    assert [(t.kind, t.weight) for t in got.traces] == [("spike", 9)]


def test_reap_orphan_child_table(gen, tmp_path):
    conn = _start(tmp_path / "c.sqlite", "reap")
    _migrate_twice(conn)
    assert "{}__gone".format(T) not in _tables(conn)


def test_reap_runs_without_child_tables(gen, tmp_path):
    """beacon_log declares no child table, yet its migration still reaps."""
    conn = sqlite3.connect(str(tmp_path / "d.sqlite"))
    conn.execute('CREATE TABLE "beacon_log_table__stray" ("owner" INTEGER)')
    conn.commit()
    assert _mig("beacon_log").SPEC.child_current == ()
    assert _mig("beacon_log").migrate_beacon_log(conn)
    assert "beacon_log_table__stray" not in _tables(conn)


def test_scalar_value_retype(gen, tmp_path):
    conn = _start(tmp_path / "e.sqlite", "scalar_retype")
    _migrate_twice(conn)
    assert _cols(conn, T + "__samples")["value"] == "INTEGER"
    assert list(_read(conn).samples) == [42, 7]


def test_map_key_and_value_retype(gen, tmp_path):
    conn = _start(tmp_path / "f.sqlite", "map_retype")
    _migrate_twice(conn)
    cols = _cols(conn, T + "__gauges")
    assert (cols["key"], cols["value"]) == ("TEXT", "INTEGER")
    assert dict(_read(conn).gauges) == {"7": 42, "8": 99}


def test_composed_add_drop_retype(gen, tmp_path):
    conn = _start(tmp_path / "g.sqlite", "composed_retype")
    _migrate_twice(conn)
    cols = _cols(conn, T + "__traces")
    assert cols["kind"] == "TEXT" and "weight" in cols and "note" not in cols
    assert [t.kind for t in _read(conn).traces] == ["5", "8"]


HAVE_SOCI = P.HAVE_CPP and os.path.exists("/usr/include/soci/soci.h")


@pytest.fixture(scope="module")
def cpp_migrator(gen, tmp_path_factory):
    if not HAVE_SOCI:
        pytest.skip("needs g++ + SOCI sqlite3 + protobuf")
    cpp_root = os.path.join(gen, "generated", "cpp")
    d = tmp_path_factory.mktemp("cpp_mig_children")
    prog = d / "mig.cpp"
    prog.write_text(
        '#include "migrate/telemetry_{h}_migrate.h"\n'
        "#include <soci/soci.h>\n#include <soci/sqlite3/soci-sqlite3.h>\n"
        "int main(int, char** argv) {{\n"
        "    ::soci::session db(::soci::sqlite3, argv[1]);\n"
        "    return ::harpia::db::migrate_telemetry(db) ? 0 : 3;\n"
        "}}\n".format(h=HASH))
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = d / "mig"
    pbs = [os.path.join(cpp_root, "protofiles", "{}_{}.pb.cc".format(n, HASH))
           for n in ("telemetry", "trace_row")]
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(prog), *pbs, "-o", str(exe),
                        "-lsoci_core", "-lsoci_sqlite3", *flags, "-lpthread", "-ldl"],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    return str(exe)


@pytest.mark.parametrize("case", sorted(STARTS))
def test_same_end_state_as_cpp(case, gen, cpp_migrator, tmp_path):
    cpp_db, py_db = tmp_path / "cpp.sqlite", tmp_path / "py.sqlite"
    _start(cpp_db, case).close()
    r = subprocess.run([cpp_migrator, str(cpp_db)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    conn = _start(py_db, case)
    _mig().migrate_telemetry(conn)
    assert _state(conn) == _state(sqlite3.connect(str(cpp_db)))
