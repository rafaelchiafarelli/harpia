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
- 2b: ``journey`` (multi-level embed), ``top_users`` (FK) and ``outpost``
  (an FK inside an embed) round-trip every persisted column, FK children
  through their own DAO; an unset FK stays absent with no phantom child
  row. g++ + SOCI: C++-written rows read identically in Python and
  Python-written rows read identically in C++.
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


EMBED_FK = ("journey", "top_users", "outpost")


def _all_daos(gen):
    out = {}
    for f in sorted(os.listdir(os.path.join(P.py_root(gen), "harpia_generated", "db"))):
        if f.endswith("_dao.py"):
            name = f[:-len("_{}_dao.py".format(HASH))]
            out[name] = dao_class(name)
    return out


def _fresh_db(gen, path):
    conn = sqlite3.connect(str(path))
    for cls in _all_daos(gen).values():
        cls(conn).create_table()
    return conn


def persisted_view(dao_cls, msg):
    """{column: value} of what ``dao_cls`` stores for ``msg`` (FK columns ->
    the child's own view, or None when absent)."""
    from harpia_runtime.db import dao as rt
    view = {}
    for col in dao_cls.COLUMNS:
        if col.fk is None:
            view[col.name] = rt.column_value(msg, col)
        else:
            child_cls = rt.dao_class(col.fk)
            view[col.name] = (persisted_view(child_cls, rt._child(msg, col))
                              if rt._has_child(msg, col) else None)
    return view


def _unique_ids(msg, counter):
    """Give every nested message's ID_<hash> a distinct value (populate()
    repeats the same one, which collides once children are rows)."""
    for f in msg.DESCRIPTOR.fields:
        if f.name == PK:
            counter[0] += 1
            setattr(msg, PK, counter[0])
        elif f.cpp_type == f.CPPTYPE_MESSAGE:
            is_map = f.message_type.GetOptions().map_entry
            items = getattr(msg, f.name)
            if is_map:
                if f.message_type.fields_by_name["value"].cpp_type == f.CPPTYPE_MESSAGE:
                    for k in items:
                        _unique_ids(items[k], counter)
            elif f.label == f.LABEL_REPEATED:
                for item in items:
                    _unique_ids(item, counter)
            elif msg.HasField(f.name):
                _unique_ids(items, counter)


def _populated(cls, pk):
    m = P.populate(cls())
    _unique_ids(m, [1000])
    setattr(m, PK, pk)
    return m


@pytest.mark.parametrize("name", EMBED_FK)
def test_embed_fk_round_trip(name, gen, msgs, tmp_path):
    cls, dao_cls = msgs[name], dao_class(name)
    dao = dao_cls(_fresh_db(gen, tmp_path / "db.sqlite"))
    m = _populated(cls, 11)
    assert dao.create(m)
    got = cls()
    assert dao.read(11, got)
    assert persisted_view(dao_cls, got) == persisted_view(dao_cls, m)
    fks = [c for c in dao_cls.COLUMNS if c.fk]
    assert fks or any(len(c.path) > 1 for c in dao_cls.COLUMNS), name
    changed = _populated(cls, 11)
    for c in dao_cls.COLUMNS:
        if c.fk is None and c.name != PK and len(c.path) > 1:
            from harpia_runtime.db import dao as rt
            owner = rt._owner(changed, c.path, True)
            f = owner.DESCRIPTOR.fields_by_name[c.path[-1]]
            if f.cpp_type == f.CPPTYPE_STRING:
                setattr(owner, c.path[-1], "changed")
    assert dao.update(changed)
    got = cls()
    dao.read(11, got)
    assert persisted_view(dao_cls, got) == persisted_view(dao_cls, changed)
    assert [persisted_view(dao_cls, x) for x in dao.list()] == [persisted_view(dao_cls, got)]


@pytest.mark.parametrize("name", ("top_users", "outpost"))
def test_unset_fk_stays_absent(name, gen, msgs, tmp_path):
    from harpia_runtime.db import dao as rt
    cls, dao_cls = msgs[name], dao_class(name)
    conn = _fresh_db(gen, tmp_path / "db.sqlite")
    m = _populated(cls, 5)
    for col in dao_cls.COLUMNS:
        if col.fk:
            rt._owner(m, col.path, True).ClearField(col.path[-1])
            child_table = rt.dao_class(col.fk).TABLE
    assert dao_cls(conn).create(m)
    assert conn.execute('SELECT COUNT(*) FROM "{}"'.format(child_table)).fetchone()[0] == 0
    got = cls()
    assert dao_cls(conn).read(5, got)
    for col in dao_cls.COLUMNS:
        if col.fk:
            assert not rt._has_child(got, col), col.name


@pytest.mark.skipif(not HAVE_SOCI, reason="needs g++ + SOCI sqlite3 + protobuf")
@pytest.mark.parametrize("name", EMBED_FK)
def test_embed_fk_cross_language(name, gen, msgs, tmp_path):
    names = ("journey", "top_users", "vip_users", "outpost", "crew")
    cls, dao_cls = msgs[name], dao_class(name)
    m = _populated(cls, 21)
    # C++ writes, Python reads == C++ reads
    db1 = tmp_path / "c.sqlite"
    _fresh_db(gen, db1).close()
    P.cpp_dao(gen, names, "write", name, db1, m.SerializeToString().hex())
    py = cls()
    assert dao_cls(sqlite3.connect(str(db1))).read(21, py)
    cpp = cls.FromString(P.cpp_dao(gen, names, "read", name, db1, "21"))
    assert _same(dao_cls, py, cpp)
    # Python writes, C++ reads == Python reads
    db2 = tmp_path / "p.sqlite"
    conn = _fresh_db(gen, db2)
    dao_cls(conn).create(m)
    py2 = cls()
    dao_cls(conn).read(21, py2)
    assert _same(dao_cls, cls.FromString(P.cpp_dao(gen, names, "read", name, db2, "21")), py2)


def _same(dao_cls, a, b):
    """Equal as far as the Python DAO persists (child tables: task 2c)."""
    return persisted_view(dao_cls, a) == persisted_view(dao_cls, b)
