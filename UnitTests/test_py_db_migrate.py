"""Generated Python schema migrations (python-target / py-database task 5a):
``harpia_generated/migrate/<name>_<hash>_migrate.py`` over
``harpia_runtime.db.migrate``. Uses the fixture's ``beacon_log`` (its
``label`` carries ``renamed_from[handle]``), starting from hand-built older
table states, the same way ``test_stage8_db.py`` drives the C++ migration.

Image-gated (python protobuf + protoc), SQLite:
- rename keeps the data, a stray column is dropped, missing columns added,
  a ``TEXT`` column retyped to ``INTEGER`` with its rows CAST across, the
  version row stamped, and a second run is idempotent;
- ``data_transform`` sees the new column (added) and the retiring one (not
  yet dropped): the split-column ordering;
- a failing ``data_transform`` rolls the whole migration back.

g++ + SOCI: from the same starting databases, the C++ and the Python
migrations end in the same schema, rows and ``_harpia_schema_version`` row.
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
T = "beacon_log_table"
ID = "ID_" + HASH

# hand-built older states of beacon_log_table
STARTS = {
    "rename_drop_add": [
        'CREATE TABLE "{t}" ("{id}" INTEGER PRIMARY KEY, "handle" TEXT, "legacy_note" TEXT);',
        "INSERT INTO \"{t}\" VALUES (1, 'north', 'obsolete');",
    ],
    "retype": [
        'CREATE TABLE "{t}" ("{id}" INTEGER PRIMARY KEY, "label" TEXT, "strength" TEXT);',
        "INSERT INTO \"{t}\" VALUES (1, 'east', '42');",
    ],
    "fresh": [],
}


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_migrate"))
    P.fixture_messages(P.py_root(g))  # puts the generated tree on sys.path
    return g


def _mig():
    return importlib.import_module("harpia_generated.migrate.beacon_log_{}_migrate".format(HASH))


def _start(path, case):
    conn = sqlite3.connect(str(path))
    for sql in STARTS[case]:
        conn.execute(sql.format(t=T, id=ID))
    conn.commit()
    return conn


def _state(conn):
    cols = [tuple(r[1:3]) for r in conn.execute("PRAGMA table_info(\"{}\")".format(T))]
    rows = conn.execute('SELECT * FROM "{}" ORDER BY 1'.format(T)).fetchall()
    ver = conn.execute('SELECT "name", "version" FROM "_harpia_schema_version"').fetchall()
    return cols, rows, ver


def test_rename_drop_add_and_idempotent(gen, tmp_path):
    conn = _start(tmp_path / "a.sqlite", "rename_drop_add")
    m = _mig()
    assert m.migrate_beacon_log(conn)
    cols, rows, ver = _state(conn)
    assert [c for c, _ in cols] == list(m.SPEC.current_columns)
    assert ver == [(T, HASH)]
    dao = importlib.import_module("harpia_generated.db.beacon_log_{}_dao".format(HASH))
    got = dao.beacon_log()
    assert dao.beacon_log_dao(conn).read(1, got) and got.label == "north"
    assert m.migrate_beacon_log(conn)  # idempotent
    assert _state(conn) == (cols, rows, ver)


def test_retype_casts_rows(gen, tmp_path):
    conn = _start(tmp_path / "b.sqlite", "retype")
    _mig().migrate_beacon_log(conn)
    cols, rows, _ = _state(conn)
    assert dict(cols)["strength"] == "INTEGER"
    strength = [c for c, _ in cols].index("strength")
    assert rows[0][strength] == 42 and isinstance(rows[0][strength], int)


def test_data_transform_order_split_column(gen, tmp_path):
    conn = _start(tmp_path / "c.sqlite", "rename_drop_add")
    seen = {}

    def transform(c):
        names = {r[1] for r in c.execute('PRAGMA table_info("{}")'.format(T))}
        seen["added"] = "strength" in names        # ADD already ran
        seen["retiring"] = "legacy_note" in names  # DROP has not run yet
        c.execute('UPDATE "{}" SET "strength" = length("legacy_note")'.format(T))

    _mig().migrate_beacon_log(conn, data_transform=transform)
    assert seen == {"added": True, "retiring": True}
    cols, rows, _ = _state(conn)
    assert "legacy_note" not in dict(cols)
    assert rows[0][[c for c, _ in cols].index("strength")] == len("obsolete")


def test_failing_transform_rolls_back(gen, tmp_path):
    conn = _start(tmp_path / "d.sqlite", "rename_drop_add")
    before = [tuple(r) for r in conn.execute('PRAGMA table_info("{}")'.format(T))]

    def boom(c):
        raise RuntimeError("transform failed")

    with pytest.raises(RuntimeError):
        _mig().migrate_beacon_log(conn, data_transform=boom)
    assert [tuple(r) for r in conn.execute('PRAGMA table_info("{}")'.format(T))] == before


HAVE_SOCI = P.HAVE_CPP and os.path.exists("/usr/include/soci/soci.h")


@pytest.fixture(scope="module")
def cpp_migrator(gen, tmp_path_factory):
    if not HAVE_SOCI:
        pytest.skip("needs g++ + SOCI sqlite3 + protobuf")
    cpp_root = os.path.join(gen, "generated", "cpp")
    d = tmp_path_factory.mktemp("cpp_mig")
    prog = d / "mig.cpp"
    prog.write_text(
        '#include "migrate/beacon_log_{h}_migrate.h"\n'
        "#include <soci/soci.h>\n#include <soci/sqlite3/soci-sqlite3.h>\n"
        "int main(int, char** argv) {{\n"
        "    ::soci::session db(::soci::sqlite3, argv[1]);\n"
        "    return ::harpia::db::migrate_beacon_log(db) ? 0 : 3;\n"
        "}}\n".format(h=HASH))
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = d / "mig"
    pb = os.path.join(cpp_root, "protofiles", "beacon_log_{}.pb.cc".format(HASH))
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(prog), pb, "-o", str(exe),
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
    _mig().migrate_beacon_log(conn)
    assert _state(conn) == _state(sqlite3.connect(str(cpp_db)))
