"""Generated Python bulk import/export (python-target / py-database task 6):
``harpia_generated/dbio/<name>_<hash>_dbio.py`` over
``harpia_runtime.db.dbio``, the port of the C++ ``dbio/<name>_<hash>_dbio.h``.

Image-gated (python protobuf + protoc), SQLite:
- export → import into an empty database round-trips every row (scalar,
  embed/FK, map / repeated / repeated-composed child tables), for JSON and
  XML, and the import returns the row count;
- an empty table exports ``""`` / ``<name_list></name_list>``, and those
  import 0 rows; blank NDJSON lines are skipped;
- malformed JSON / XML raises ``ValueError`` and writes nothing; a duplicate
  key raises and rolls the whole import back.

g++ + SOCI + tinyxml2: from the same rows, the C++ and Python exports are
byte-identical (XML) and cross-parse-equal per line (NDJSON); a C++ export
imports in Python and a Python export imports in C++, each read back equal.
"""
import concurrent.futures
import glob
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
from UnitTests.test_py_db_dao import _unique_ids  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
NAMES = ("users", "journey", "top_users", "outpost", "data", "telemetry", "shipment")
# every message a NAMES DAO reaches through an FK (the C++ program links them)
LINKED = NAMES + ("vip_users", "crew")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("py_dbio"))


@pytest.fixture(scope="module")
def msgs(gen):
    return P.fixture_messages(P.py_root(gen))


def _dbio(name):
    return importlib.import_module("harpia_generated.dbio.{}_{}_dbio".format(name, HASH))


def _dao(name):
    mod = importlib.import_module("harpia_generated.db.{}_{}_dao".format(name, HASH))
    return getattr(mod, name + "_dao")


def _fresh_db(gen, path, name):
    """A database with ``name``'s tables and those every DAO its FKs reach
    (users and top_users share one table name, so never create them all)."""
    from harpia_runtime.db import dao as rt
    conn = sqlite3.connect(str(path))
    todo, seen = [_dao(name)], set()
    while todo:
        cls = todo.pop()
        if cls in seen:
            continue
        seen.add(cls)
        cls(conn).create_table()
        todo += [rt.dao_class(r) for r in
                 [c.fk for c in cls.COLUMNS] + [c.fk for c in cls.CHILDREN] if r]
    return conn


def _rows(cls, n=3):
    rows = []
    for i in range(n):
        m = P.populate(cls())
        _unique_ids(m, [100000 * (i + 1)])
        setattr(m, PK, i + 1)
        rows.append(m)
    return rows


def _seeded(gen, path, name, rows):
    conn = _fresh_db(gen, path, name)
    dao = _dao(name)(conn)
    for m in rows:
        assert dao.create(m)
    return conn


def _listed(conn, name):
    return _dao(name)(conn).list()


@pytest.mark.parametrize("fmt", ["json", "xml"])
@pytest.mark.parametrize("name", NAMES)
def test_export_import_round_trip(name, fmt, gen, msgs, tmp_path):
    rows = _rows(msgs[name])
    src = _seeded(gen, tmp_path / "src.sqlite", name, rows)
    io = _dbio(name)
    text = getattr(io, "export_" + fmt)(_dao(name)(src))
    dst = _fresh_db(gen, tmp_path / "dst.sqlite", name)
    assert getattr(io, "import_" + fmt)(_dao(name)(dst), text) == len(rows)
    assert _listed(dst, name) == _listed(src, name)
    # the import is complete: re-exporting gives the same text
    assert getattr(io, "export_" + fmt)(_dao(name)(dst)) == text


def test_empty_table_and_blank_lines(gen, msgs, tmp_path):
    io, dao = _dbio("users"), _dao("users")(_fresh_db(gen, tmp_path / "e.sqlite", "users"))
    assert io.export_json(dao) == ""
    assert io.export_xml(dao) == "<users_list></users_list>"
    assert io.import_json(dao, "") == 0
    assert io.import_xml(dao, "<users_list></users_list>") == 0
    one = _rows(msgs["users"], 1)[0]
    line = io.export_json(_dao("users")(_seeded(gen, tmp_path / "s.sqlite", "users", [one])))
    assert io.import_json(dao, "\n" + line + "\n\n") == 1
    assert dao.list() == [one]


@pytest.mark.parametrize("fmt,bad", [
    ("json", '{{"name": "ok", "{pk}": 1}}\n{{not json\n'),
    ("xml", "<users_list><users><name>x</name></users>"),
])
def test_malformed_input_writes_nothing(fmt, bad, gen, tmp_path):
    dao = _dao("users")(_fresh_db(gen, tmp_path / "m.sqlite", "users"))
    with pytest.raises(ValueError):
        getattr(_dbio("users"), "import_" + fmt)(dao, bad.format(pk=PK))
    assert dao.list() == []


def test_duplicate_key_rolls_back(gen, msgs, tmp_path):
    rows = _rows(msgs["users"], 2)
    text = _dbio("users").export_json(
        _dao("users")(_seeded(gen, tmp_path / "s.sqlite", "users", rows)))
    dst = _seeded(gen, tmp_path / "d.sqlite", "users", rows[1:])  # key 2 already there
    with pytest.raises(sqlite3.IntegrityError):
        _dbio("users").import_json(_dao("users")(dst), text)
    assert [getattr(m, PK) for m in _listed(dst, "users")] == [2]


# -- C++ parity ----------------------------------------------------------------
HAVE_SOCI = P.HAVE_CPP and os.path.exists("/usr/include/soci/soci.h")

_MAIN = r'''
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
%(includes)s

template <class Dao>
int run(const std::string& mode, ::soci::session& db, const char* file) {
    Dao dao(db);
    std::string text;
    if (mode == "export_json") { if (!harpia::dbio::export_json(dao, &text)) return 3; }
    else if (mode == "export_xml") { if (!harpia::dbio::export_xml(dao, &text)) return 3; }
    else {
        std::ifstream in(file, std::ios::binary);
        std::stringstream ss; ss << in.rdbuf();
        bool ok = mode == "import_json" ? harpia::dbio::import_json(dao, ss.str())
                                        : harpia::dbio::import_xml(dao, ss.str());
        return ok ? 0 : 4;
    }
    std::cout << text;
    return 0;
}

int main(int argc, char** argv) {
    if (argc < 4) return 2;
    std::string mode = argv[1], type = argv[2];
    ::soci::session db(::soci::sqlite3, argv[3]);
    const char* file = argc > 4 ? argv[4] : "";
%(dispatch)s
    return 2;
}
'''


@pytest.fixture(scope="module")
def cpp_dbio(gen, tmp_path_factory):
    if not HAVE_SOCI:
        pytest.skip("needs g++ + SOCI sqlite3 + protobuf")
    cpp_root = os.path.join(gen, "generated", "cpp")
    work = str(tmp_path_factory.mktemp("cpp_dbio"))
    src = os.path.join(work, "dbio.cc")
    with open(src, "w") as f:
        f.write(_MAIN % {
            "includes": "\n".join('#include "dbio/{}_{}_dbio.h"'.format(n, HASH)
                                  for n in NAMES),
            "dispatch": "\n".join(
                '    if (type == "{0}") return run<harpia::db::{0}_dao>(mode, db, file);'
                .format(n) for n in NAMES)})
    sources = sorted(s for s in glob.glob(os.path.join(cpp_root, "protofiles", "*.pb.cc"))
                     if not s.endswith(".grpc.pb.cc"))
    sources += [src, os.path.join(TINYXML2, "tinyxml2.cpp")]
    cflags = ["-std=c++17", "-O0", "-I", cpp_root, "-I", TINYXML2] + P._pkgconfig("--cflags")

    def _compile(s):
        obj = os.path.join(work, os.path.basename(s) + ".o")
        r = subprocess.run(["g++", *cflags, "-c", s, "-o", obj],
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, "{}:\n{}".format(s, r.stderr)
        return obj

    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as ex:
        objs = list(ex.map(_compile, sources))
    exe = os.path.join(work, "dbio")
    r = subprocess.run(["g++", *objs, "-o", exe, "-lsoci_core", "-lsoci_sqlite3",
                        *P._pkgconfig("--libs"), "-lcrypto", "-pthread", "-ldl"],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    return exe


def _cpp(exe, mode, name, db, file=""):
    r = subprocess.run([exe, mode, name, str(db), str(file)], capture_output=True,
                       timeout=60)
    assert r.returncode == 0, "dbio {} {} -> {}\n{}".format(mode, name, r.returncode,
                                                            r.stderr.decode())
    return r.stdout.decode()


@pytest.mark.parametrize("name", NAMES)
def test_exports_match_cpp(name, gen, msgs, cpp_dbio, tmp_path):
    cls = msgs[name]
    db = tmp_path / "src.sqlite"
    dao = _dao(name)(_seeded(gen, db, name, _rows(cls)))
    io = _dbio(name)
    assert io.export_xml(dao) == _cpp(cpp_dbio, "export_xml", name, db)
    py_lines = io.export_json(dao).split("\n")
    cpp_lines = _cpp(cpp_dbio, "export_json", name, db).split("\n")
    from harpia_runtime.json import from_json
    assert len(py_lines) == len(cpp_lines)
    for a, b in zip(py_lines, cpp_lines):
        pa, pb = cls(), cls()
        assert (not a and not b) or (from_json(a, pa) and from_json(b, pb) and pa == pb)


@pytest.mark.parametrize("fmt", ["json", "xml"])
@pytest.mark.parametrize("name", NAMES)
def test_cross_language_import(name, fmt, gen, msgs, cpp_dbio, tmp_path):
    rows = _rows(msgs[name])
    src = tmp_path / "src.sqlite"
    expected = _listed(_seeded(gen, src, name, rows), name)
    io = _dbio(name)
    # C++ export -> Python import
    cpp_text = _cpp(cpp_dbio, "export_" + fmt, name, src)
    py_db = _fresh_db(gen, tmp_path / "py.sqlite", name)
    assert getattr(io, "import_" + fmt)(_dao(name)(py_db), cpp_text) == len(rows)
    assert _listed(py_db, name) == expected
    # Python export -> C++ import
    f = tmp_path / ("export." + fmt)
    f.write_text(getattr(io, "export_" + fmt)(_dao(name)(sqlite3.connect(str(src)))))
    cpp_db = tmp_path / "cpp.sqlite"
    _fresh_db(gen, cpp_db, name).close()
    _cpp(cpp_dbio, "import_" + fmt, name, cpp_db, f)
    assert _listed(sqlite3.connect(str(cpp_db)), name) == expected
