"""Generated Python CRUDL DAOs (python-target / py-database tasks 2a-2c):
``harpia_generated/db/<name>_<hash>_dao.py`` over ``harpia_runtime.db.dao``.

Image-gated (python protobuf + protoc), against an SQLite file:

- 2a: every all-scalar fixture message (``users``, ``beacon_log``, ``crew``,
  ``patient_vitals``) round-trips create / read / update / list / remove,
  with pagination bounds; ``update`` / ``remove`` of a missing row return
  False; a duplicate key raises; the table a Python DAO creates has exactly
  the columns of the C++ ``database/<name>_<hash>_table.sql`` (every table).
- g++ + SOCI: a row written by the C++ ``users_dao`` reads back identically
  through the Python DAO on the same SQLite file.
"""
import importlib
import os
import shutil
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
PK = "ID_" + HASH
ALL_SCALAR = ("users", "beacon_log", "crew", "patient_vitals")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("py_dao"))


@pytest.fixture(scope="module")
def msgs(gen):
    return P.fixture_messages(P.py_root(gen))


def dao_class(name):
    mod = importlib.import_module("harpia_generated.db.{}_{}_dao".format(name, HASH))
    return getattr(mod, name + "_dao")


def _scalar_msg(cls, pk, salt):
    m = P.populate(cls())
    setattr(m, PK, pk)
    for f in m.DESCRIPTOR.fields:
        if f.cpp_type == f.CPPTYPE_STRING and f.label != f.LABEL_REPEATED:
            setattr(m, f.name, "{}-{}".format(f.name, salt))
    return m


@pytest.mark.parametrize("name", ALL_SCALAR)
def test_crudl_round_trip(name, msgs, tmp_path):
    cls = msgs[name]
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    dao = dao_class(name)(conn)
    dao.create_table()
    rows = [_scalar_msg(cls, pk, pk) for pk in (1, 2, 3, 4, 5)]
    for m in rows:
        assert dao.create(m) is True
    got = cls()
    assert dao.read(3, got) and got == rows[2]
    assert not dao.read(99, cls())

    changed = _scalar_msg(cls, 3, "new")
    assert dao.update(changed)
    got = cls()
    dao.read(3, got)
    assert got == changed
    assert not dao.update(_scalar_msg(cls, 42, "x"))

    listed = dao.list()
    assert [getattr(m, PK) for m in listed] == [1, 2, 3, 4, 5]
    assert [getattr(m, PK) for m in dao.list(1, 2)] == [2, 3]
    assert [getattr(m, PK) for m in dao.list(4, 10)] == [5]
    assert dao.list(10, 2) == []
    assert [getattr(m, PK) for m in dao.list(offset=2)] == [3, 4, 5]

    assert dao.remove(2) and not dao.remove(2)
    assert not dao.read(2, cls())
    with pytest.raises(sqlite3.IntegrityError):
        dao.create(rows[0])
    # the failed insert was rolled back, the connection is still usable
    assert len(dao.list()) == 4
    dao.drop_table()
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def _columns(conn, table):
    return [(r[1], r[2], r[5]) for r in conn.execute('PRAGMA table_info("{}")'.format(table))]


def test_table_matches_cpp_schema(gen, msgs, tmp_path):
    sql_dir = os.path.join(gen, "database")
    checked = 0
    for f in sorted(os.listdir(os.path.join(P.py_root(gen), "harpia_generated", "db"))):
        if not f.endswith("_dao.py"):
            continue
        name = f[:-len("_{}_dao.py".format(HASH))]
        dao = dao_class(name)
        a = sqlite3.connect(":memory:")
        dao(a).create_table()
        b = sqlite3.connect(":memory:")
        b.executescript(open(os.path.join(sql_dir, "{}_{}_table.sql".format(name, HASH))).read())
        assert _columns(a, dao.TABLE) == _columns(b, dao.TABLE), name
        checked += 1
    assert checked >= 10


HAVE_SOCI = P.HAVE_CPP and shutil.which("g++") is not None and os.path.exists(
    "/usr/include/soci/soci.h")


@pytest.mark.skipif(not HAVE_SOCI, reason="needs g++ + SOCI sqlite3 + protobuf")
def test_cpp_written_row_reads_in_python(gen, msgs, tmp_path):
    cpp_root = os.path.join(gen, "generated", "cpp")
    db_file = tmp_path / "shared.sqlite"
    prog = tmp_path / "writer.cpp"
    prog.write_text(
        '#include "db/users_{h}_crudl.h"\n'
        "#include <soci/soci.h>\n"
        "#include <soci/sqlite3/soci-sqlite3.h>\n"
        "int main(int, char** argv) {{\n"
        "    ::soci::session db(::soci::sqlite3, argv[1]);\n"
        "    harpia::db::users_dao dao(db);\n"
        "    if (!dao.create_table()) return 2;\n"
        "    ::users a; a.set_id_{h}(7); a.set_name(\"n\\xc3\\xa9o 'q'\");\n"
        "    a.set_address(\"matrix\"); a.set_status_{h}(\"ok\");\n"
        "    return dao.create(a) ? 0 : 3;\n"
        "}}\n".format(h=HASH))
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "writer"
    pb = os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH))
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(prog), pb, "-o", str(exe),
                        "-lsoci_core", "-lsoci_sqlite3", *flags, "-lpthread", "-ldl"],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    r = subprocess.run([str(exe), str(db_file)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr

    got = msgs["users"]()
    assert dao_class("users")(sqlite3.connect(str(db_file))).read(7, got)
    want = msgs["users"](name="néo 'q'", address="matrix")
    setattr(want, PK, 7)
    setattr(want, "STATUS_" + HASH, "ok")
    assert got == want
