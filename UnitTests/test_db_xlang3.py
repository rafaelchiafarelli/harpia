"""python-target / tri-language-interop task 2: C++, Java and Python DAOs on
one shared database.

One schema, generated twice -- ``HARPIA_GEN_LANG=python`` (C++ + Python) and
``HARPIA_GEN_LANG=java`` (C++ + Java); same hash, identical C++ tree. Every
table message gets its own database (``users`` and ``top_users`` share the
table name ``user_table``, so they can't live in one file), shared by the
three languages:

- **cross read/write**: for every table message, the row one language's DAO
  writes reads back through the other two; the C++ and Python reads are
  equal messages, the Java read equals them where Java participates, and
  what was stored is what was written (``persisted_view``);
- **Java's scope is asserted, not hidden**: Java's DAOs persist top-level
  scalar/enum columns only and have no phi support (``JavaDatabase/
  CLAUDE.md``). A message with an embed/FK column, a child table or a phi
  column is skipped for Java, and the test checks the reason really holds
  (deferred list in the Java DAO header, child tables / encryption absent
  from it). Tables are created through C++ or Python, never Java (the Java
  table of a message with deferred columns is narrower);
- **phi** (``patient_vitals``, ``alarm_event``): C++ and Python share one
  ``LocalKeyProvider`` store; the stored phi columns are ``enc:v1:``
  ciphertext whoever wrote them;
- **migration**: ``beacon_log`` starts in a hand-built older state
  (``test_py_db_migrate.STARTS``) and is migrated by C++ or by Python; C++
  and Python read the old row equally, and all three languages write rows
  into the migrated table and read each other's equally (Java has no
  migration of its own -- see ``JavaDatabase/CLAUDE.md``). Java reading the
  pre-migration row is a strict xfail: the columns the migration added are
  NULL there and ``JdbcBind.extract`` NPEs on a NULL string (JAVA FINDING,
  NEXT_SESSION item 44);
- **PostgreSQL** (opt-in ``HARPIA_PG_DSN``, run by ``Docker/run_pg_tests.sh``):
  the same matrix and migration, every slot a throwaway DATABASE (migration
  introspection is not schema-qualified, NEXT_SESSION item 19).
  ``patient_vitals`` is a strict xfail there (item 26: its numeric phi
  column keeps a numeric PG type).

C++ and Java run as batch probes (one process per language per phase,
tab-separated requests on stdin); Python runs in-process. Gated on g++ +
SOCI + protobuf, gradle + JDK and the Python toolchain.
"""
import concurrent.futures
import glob
import importlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests._java_gradle_helpers import build_and_classpath, generate  # noqa: E402
from UnitTests.test_py_db_dao import _populated, persisted_view  # noqa: E402
from UnitTests.test_py_db_migrate import STARTS  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
LANGS = ("cpp", "python", "java")
# the messages Java's DAOs fully persist (no embed/FK, no child table, no phi)
JAVA_SCOPE = {"beacon_log", "crew", "reception_desk", "users", "vault", "vip_users"}

PG_DSN = os.environ.get("HARPIA_PG_DSN")
HAVE_SOCI = P.HAVE_CPP and os.path.exists("/usr/include/soci/soci.h")
HAVE_JAVA = shutil.which("gradle") is not None and shutil.which("java") is not None
HAVE_PG = bool(PG_DSN) and P._importable("psycopg") and shutil.which("pg_config") is not None

pytestmark = pytest.mark.skipif(
    not (HAVE_SOCI and HAVE_JAVA),
    reason="needs g++ + SOCI sqlite3 + protobuf, gradle+JDK and the Python toolchain (image)")
pg_only = pytest.mark.skipif(
    not HAVE_PG, reason="needs HARPIA_PG_DSN + psycopg + libpq (opt-in live PG)")


# -- C++ batch probe ----------------------------------------------------

_CPP = r'''
#include <cstdio>
#include <exception>
#include <iostream>
#include <string>
#include <vector>
#include <soci/soci.h>
#ifdef HARPIA_PG
#include <soci/postgresql/soci-postgresql.h>
#define HARPIA_SOCI_BACKEND ::soci::postgresql
#else
#include <soci/sqlite3/soci-sqlite3.h>
#define HARPIA_SOCI_BACKEND ::soci::sqlite3
#endif
#include "crypto/harpia_key_provider_local.h"
%(includes)s

static std::string unhex(const std::string& h) {
    std::string out;
    for (size_t i = 0; i + 1 < h.size(); i += 2)
        out += static_cast<char>(std::stoi(h.substr(i, 2), nullptr, 16));
    return out;
}

static std::string hex(const std::string& b) {
    static const char* d = "0123456789abcdef";
    std::string out;
    for (unsigned char c : b) { out += d[c >> 4]; out += d[c & 15]; }
    return out;
}

template <class Dao, class Msg>
static std::string op(Dao& dao, const std::string& mode, const std::string& arg) {
    if (mode == "create") return dao.create_table() ? "OK" : "FAIL create_table";
    if (mode == "write") {
        Msg m;
        if (!m.ParseFromString(unhex(arg))) return "FAIL parse";
        return dao.create(m) ? "OK" : "FAIL create";
    }
    Msg m;
    if (!dao.read(std::stoll(arg), &m)) return "FAIL read";
    return "OK " + hex(m.SerializeAsString());
}

// stdin: <mode>\t<type>\t<connection>\t<arg> per line; argv[1]: KEK store
int main(int, char** argv) {
    harpia::crypto::LocalKeyProvider kp(harpia::crypto::LocalKeyProviderConfig{argv[1], false, false});
    std::string line;
    while (std::getline(std::cin, line)) {
        std::vector<std::string> p;
        size_t start = 0, tab;
        while ((tab = line.find('\t', start)) != std::string::npos) {
            p.push_back(line.substr(start, tab - start));
            start = tab + 1;
        }
        p.push_back(line.substr(start));
        if (p.size() != 4) return 2;
        const std::string &mode = p[0], &type = p[1], &arg = p[3];
        std::string out;
        try {
            ::soci::session db(HARPIA_SOCI_BACKEND, p[2]);
            if (mode == "migrate") {
                if (type == "beacon_log")
                    out = ::harpia::db::migrate_beacon_log(db) ? "OK" : "FAIL migrate";
            }
%(dispatch)s
        } catch (const std::exception& e) {
            out = std::string("FAIL ") + e.what();
        }
        if (out.empty()) out = "FAIL notype";
        for (char& c : out) if (c == '\n') c = ' ';
        std::printf("%%s\n", out.c_str());
        std::fflush(stdout);
    }
    return 0;
}
'''


def _build_cpp_probe(gen, names, phi, pg):
    cpp_root = os.path.join(gen, "generated", "cpp")
    work = os.path.join(gen, "_xlang3_cpp")
    os.makedirs(work, exist_ok=True)
    includes = ['#include "db/{}_{}_crudl.h"'.format(n, HASH) for n in names]
    includes.append('#include "migrate/beacon_log_{}_migrate.h"'.format(HASH))
    dispatch = "\n".join(
        '            else if (type == "{0}") {{ harpia::db::{0}_dao dao(db{1}); '
        'out = op<harpia::db::{0}_dao, ::{0}>(dao, mode, arg); }}'
        .format(n, ", kp" if n in phi else "") for n in names)
    src = os.path.join(work, "probe.cc")
    with open(src, "w") as f:
        f.write(_CPP % {"includes": "\n".join(includes), "dispatch": dispatch})
    cflags = ["-std=c++17", "-O0", "-I", cpp_root] + P._pkgconfig("--cflags")
    libs = ["-lsoci_core", "-lsoci_sqlite3"]
    if pg:
        cflags += ["-DHARPIA_PG", "-I", subprocess.run(
            ["pg_config", "--includedir"], capture_output=True, text=True,
            check=True).stdout.strip()]
        libs = ["-lsoci_core", "-lsoci_postgresql"]
    sources = sorted(s for s in glob.glob(os.path.join(cpp_root, "protofiles", "*.pb.cc"))
                     if not s.endswith(".grpc.pb.cc")) + [src]

    def _compile(s):
        obj = os.path.join(work, os.path.basename(s) + ".o")
        r = subprocess.run(["g++", *cflags, "-c", s, "-o", obj],
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, "{}:\n{}".format(s, r.stderr)
        return obj

    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as ex:
        objs = list(ex.map(_compile, sources))
    exe = os.path.join(work, "probe")
    r = subprocess.run(["g++", *objs, "-o", exe, *libs, *P._pkgconfig("--libs"),
                        "-lcrypto", "-pthread", "-ldl"],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    return exe


# -- Java batch probe ---------------------------------------------------

_JAVA = r'''
package xlang;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;

// stdin: <mode>\t<type>\t<jdbc url>\t<arg> per line
public class DbProbe {
    static byte[] unhex(String h) {
        byte[] out = new byte[h.length() / 2];
        for (int i = 0; i < out.length; i++)
            out[i] = (byte) Integer.parseInt(h.substring(2 * i, 2 * i + 2), 16);
        return out;
    }

    static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%%02x", x & 0xff));
        return s.toString();
    }

    public static void main(String[] args) throws Exception {
        for (String drv : new String[] {"org.sqlite.JDBC", "org.postgresql.Driver"}) {
            try { Class.forName(drv); } catch (ClassNotFoundException e) { }
        }
        BufferedReader in = new BufferedReader(
            new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            String[] p = line.split("\t", -1);
            String out;
            try (Connection c = DriverManager.getConnection(p[2])) {
                out = run(c, p[0], p[1], p[3]);
            } catch (Exception e) {
                out = "FAIL " + e;
            }
            System.out.println(out.replace('\n', ' '));
            System.out.flush();
        }
    }

    static String run(Connection c, String mode, String type, String arg) throws Exception {
        switch (type) {
%(cases)s
        }
        return "FAIL notype";
    }
}
'''

_JAVA_CASE = '''\
            case "{n}": {{
                com.harpia.generated.db.{n}_dao d = new com.harpia.generated.db.{n}_dao(c);
                if (mode.equals("write"))
                    return d.create(com.harpia.generated.{n}.parseFrom(unhex(arg))) ? "OK" : "FAIL create";
                com.harpia.generated.{n}.Builder b = com.harpia.generated.{n}.newBuilder();
                return d.read(Integer.parseInt(arg), b) ? "OK " + hex(b.build().toByteArray()) : "FAIL read";
            }}'''


def _build_java_probe(java_gen, names):
    src = _JAVA % {"cases": "\n".join(_JAVA_CASE.format(n=n) for n in sorted(names))}
    return build_and_classpath(os.path.join(java_gen, "java"), {"xlang/DbProbe.java": src})


# -- one generated project per dialect ------------------------------------

def _dsn_parts(dsn):
    return dict(kv.split("=", 1) for kv in dsn.split())


class Side:
    """The generated project of one SQL dialect and its three DAO drivers."""

    def __init__(self, tmp, pg):
        backend = "postgresql" if pg else None
        self.pg = pg
        self.gen = generate(tmp / "py", lang="python", db_backend=backend)
        self.java_gen = generate(tmp / "java", lang="java", db_backend=backend)
        self.root = P.py_root(self.gen)
        self.msgs = P.fixture_messages(self.root)
        db_dir = os.path.join(self.root, "harpia_generated", "db")
        self.tables = sorted(f[:-len("_{}_dao.py".format(HASH))]
                             for f in os.listdir(db_dir) if f.endswith("_dao.py"))
        self.phi = {n for n in self.tables if self.is_phi(n)}
        self.java_scope = {n for n in self.tables if java_eligible(self.dao(n))}
        self.cpp = _build_cpp_probe(self.gen, self.tables, self.phi, pg)
        self.java_cp = _build_java_probe(self.java_gen, self.java_scope)

    def activate(self):
        P.activate(self.root)
        self.msgs = P.fixture_messages(self.root)

    def dao(self, name):
        mod = importlib.import_module("harpia_generated.db.{}_{}_dao".format(name, HASH))
        return getattr(mod, name + "_dao")

    def is_phi(self, name):
        from harpia_runtime.db.phi import PhiDao
        return issubclass(self.dao(name), PhiDao)

    def java_dao_source(self, name):
        return open(os.path.join(self.java_gen, "java", "src", "main", "java", "com", "harpia",
                                 "generated", "db", name + "_dao.java")).read()

    # a slot is one database: an SQLite file, or a PostgreSQL database name
    def connect(self, slot):
        if self.pg:
            import psycopg
            return psycopg.connect(self.cpp_target(slot))
        return sqlite3.connect(slot)

    def cpp_target(self, slot):
        if self.pg:
            from psycopg.conninfo import make_conninfo
            return make_conninfo(PG_DSN, dbname=slot)
        return slot

    def java_target(self, slot):
        if self.pg:
            p = _dsn_parts(PG_DSN)
            return "jdbc:postgresql://{}:{}/{}?user={}&password={}".format(
                p.get("host", "localhost"), p.get("port", "5432"), slot, p["user"],
                p.get("password", ""))
        return "jdbc:sqlite:" + slot

    # -- drivers: run [(mode, type, slot, arg)] -> [(ok, payload)]
    def batch(self, lang, reqs, store):
        if lang == "python":
            return [self._py(mode, n, slot, arg, store) for mode, n, slot, arg in reqs]
        if lang == "cpp":
            cmd, target = [self.cpp, store], self.cpp_target
        else:
            cmd, target = ["java", "-cp", self.java_cp, "xlang.DbProbe"], self.java_target
        lines = "".join("{}\t{}\t{}\t{}\n".format(mode, n, target(slot), arg)
                        for mode, n, slot, arg in reqs)
        r = subprocess.run(cmd, input=lines, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, "{} probe exited {}\n{}".format(lang, r.returncode, r.stderr)
        out = []
        for line in r.stdout.splitlines():
            status, _, payload = line.partition(" ")
            out.append((status == "OK", payload))
        assert len(out) == len(reqs), r.stdout[-2000:] + r.stderr[-2000:]
        return out

    def _py(self, mode, n, slot, arg, store):
        conn = self.connect(slot)
        try:
            dao_cls = self.dao(n)
            kw = {}
            if n in self.phi:
                from harpia_runtime.crypto.key_provider_local import (
                    LocalKeyProvider, LocalKeyProviderConfig)
                kw["key_provider"] = LocalKeyProvider(LocalKeyProviderConfig(store))
            if mode == "create":
                dao_cls(conn, **kw).create_table()
                ok, payload = True, ""
            elif mode == "write":
                ok = dao_cls(conn, **kw).create(self.msgs[n].FromString(bytes.fromhex(arg)))
                payload = ""
            elif mode == "read":
                m = self.msgs[n]()
                ok = dao_cls(conn, **kw).read(int(arg), m)
                payload = m.SerializeToString().hex()
            else:
                mig = importlib.import_module(
                    "harpia_generated.migrate.{}_{}_migrate".format(n, HASH))
                ok, payload = getattr(mig, "migrate_" + n)(conn), ""
            conn.commit()
            return ok, payload
        except Exception as e:  # reported like a probe FAIL line
            return False, repr(e)
        finally:
            conn.close()


def java_eligible(dao_cls):
    """Java's documented subset: every column top-level and not an FK, no
    child table, no phi column."""
    return (not getattr(dao_cls, "PHI_FIELDS", ()) and not dao_cls.CHILDREN
            and all(len(c.path) == 1 and c.fk is None for c in dao_cls.COLUMNS))


def _fk_closure(side, name, seen=None):
    """``name`` and every table its FKs reach, referenced tables first."""
    from harpia_runtime.db import dao as rt
    seen = [] if seen is None else seen
    dao_cls = side.dao(name)
    for ref in [c.fk for c in dao_cls.COLUMNS] + [c.fk for c in dao_cls.CHILDREN]:
        if ref:
            ref_name = rt.dao_class(ref).__name__[:-len("_dao")]
            if ref_name not in seen:
                _fk_closure(side, ref_name, seen)
    if name not in seen:
        seen.append(name)
    return seen


@pytest.fixture(scope="module")
def sqlite_side(tmp_path_factory):
    return Side(tmp_path_factory.mktemp("xlang3_sqlite"), pg=False)


@pytest.fixture(scope="module")
def pg_side(tmp_path_factory):
    if not HAVE_PG:
        pytest.skip("needs HARPIA_PG_DSN + psycopg + libpq (opt-in live PG)")
    return Side(tmp_path_factory.mktemp("xlang3_pg"), pg=True)


@pytest.fixture()
def pg_databases():
    """Factory of throwaway PostgreSQL databases, dropped afterwards."""
    import psycopg
    admin = psycopg.connect(PG_DSN, autocommit=True)
    made = []

    def make():
        name = "harpia_x3_" + uuid.uuid4().hex[:12]
        try:
            admin.execute('CREATE DATABASE "{}"'.format(name))
        except psycopg.Error as e:
            pytest.skip("cannot CREATE DATABASE: {}".format(e))
        made.append(name)
        return name

    yield make
    for name in made:
        admin.execute('DROP DATABASE IF EXISTS "{}" WITH (FORCE)'.format(name))
    admin.close()


def _slot_factory(side, tmp_path, pg_databases):
    if side.pg:
        return lambda name: pg_databases()
    return lambda name: str(tmp_path / (name + ".sqlite"))


# -- the matrix -----------------------------------------------------------

def _ok(results, what):
    bad = [(i, p) for i, (ok, p) in enumerate(results) if not ok]
    assert not bad, "{}: {}".format(what, bad)


def _matrix(side, writer, new_slot, store, names):
    side.activate()
    if writer == "java":
        names = [n for n in names if n in side.java_scope]
    slots = {n: new_slot(n) for n in names}
    # tables come from C++ or Python -- the writer's own DDL, C++'s for Java
    creator = "cpp" if writer == "java" else writer
    _ok(side.batch(creator, [("create", t, slots[n], "")
                             for n in names for t in _fk_closure(side, n)], store),
        creator + " create_table")
    originals = {n: _populated(side.msgs[n], 7) for n in names}
    _ok(side.batch(writer, [("write", n, slots[n], originals[n].SerializeToString().hex())
                            for n in names], store), writer + " write")

    reads = {}
    for reader in LANGS:
        scope = [n for n in names if reader != "java" or n in side.java_scope]
        res = side.batch(reader, [("read", n, slots[n], "7") for n in scope], store)
        _ok(res, "{} reads {}'s rows".format(reader, writer))
        reads[reader] = {n: side.msgs[n].FromString(bytes.fromhex(p))
                         for n, (_, p) in zip(scope, res)}

    for n in names:
        dao_cls = side.dao(n)
        assert reads["python"][n] == reads["cpp"][n], (n, writer)
        assert persisted_view(dao_cls, reads["python"][n]) == \
            persisted_view(dao_cls, originals[n]), (n, writer)
        if n in side.java_scope:
            assert reads["java"][n] == reads["cpp"][n], (n, writer)
            assert reads["java"][n] == originals[n], (n, writer)
        if n in side.phi:
            conn = side.connect(slots[n])
            for col in dao_cls.PHI_FIELDS:
                stored = conn.execute('SELECT "{}" FROM "{}"'.format(col, dao_cls.TABLE)) \
                    .fetchone()[0]
                assert str(stored).startswith("enc:v1:"), (n, col, writer, stored)
            conn.close()
    return names


@pytest.mark.parametrize("writer", LANGS)
def test_sqlite_cross_read_write(writer, sqlite_side, tmp_path):
    names = _matrix(sqlite_side, writer, _slot_factory(sqlite_side, tmp_path, None),
                    str(tmp_path / "keks"), sqlite_side.tables)
    expected = JAVA_SCOPE if writer == "java" else set(sqlite_side.tables)
    assert set(names) == expected
    assert len(sqlite_side.tables) == 14 and sqlite_side.phi == {"alarm_event", "patient_vitals"}


def test_java_scope_is_asserted(sqlite_side):
    """Java participates exactly for its documented subset; every skipped
    message has a real reason, visible in the Java DAO itself."""
    side = sqlite_side
    side.activate()
    assert side.java_scope == JAVA_SCOPE
    for n in side.tables:
        dao_cls, src = side.dao(n), side.java_dao_source(n)
        deferred = re.search(r"see JavaDatabase/CLAUDE\.md\): (.*)", src).group(1)
        if n in JAVA_SCOPE:
            assert deferred == "none", n
            # Java's own table has exactly the C++/Python columns
            ddl = re.search(r'CREATE_TABLE_SQL = "((?:[^"\\]|\\.)*)";', src).group(1)
            a, b = sqlite3.connect(":memory:"), sqlite3.connect(":memory:")
            a.execute(ddl.replace('\\"', '"'))
            dao_cls(b).create_table()
            info = 'PRAGMA table_info("{}")'.format(dao_cls.TABLE)
            assert a.execute(info).fetchall() == b.execute(info).fetchall(), n
            continue
        reasons = []
        nested = [c.name for c in dao_cls.COLUMNS if len(c.path) > 1 or c.fk]
        if nested:
            assert all(c in deferred for c in nested), (n, nested, deferred)
            reasons.append("embed/fk")
        if dao_cls.CHILDREN:
            # the Java DAO never touches the child tables (its header's
            # deferred list doesn't name them -- NEXT_SESSION item 44)
            for child in dao_cls.CHILDREN:
                assert child.insert_sql.split('"')[1] not in src, (n, child)
            reasons.append("children")
        if getattr(dao_cls, "PHI_FIELDS", ()):
            assert "KeyProvider" not in src and "enc:v1" not in src, n
            reasons.append("phi")
        assert reasons, n


# A row that predates the migration has NULL in every column the migration
# added (here STATUS_/ERROR_/ORIGINATOR); Java's JdbcBind.extract passes a NULL
# string to Builder.setField -> NullPointerException, where C++ and Python
# read the default. JAVA FINDING (NEXT_SESSION item 44) -- strict so a fix shows.
_JAVA_NULL_TEXT = pytest.mark.xfail(
    strict=True, reason="JAVA FINDING (item 44): JdbcBind.extract NPEs on a NULL text column")


@pytest.mark.parametrize("migrator", ("cpp", "python"))
@pytest.mark.parametrize("case", ("rename_drop_add", "retype"))
def test_sqlite_migration_then_cross_read(case, migrator, sqlite_side, tmp_path):
    _migration(sqlite_side, case, migrator, str(tmp_path / "beacon.sqlite"),
               str(tmp_path / "keks"))


@_JAVA_NULL_TEXT
@pytest.mark.parametrize("migrator", ("cpp", "python"))
def test_sqlite_java_reads_pre_migration_row(migrator, sqlite_side, tmp_path):
    _migration(sqlite_side, "rename_drop_add", migrator, str(tmp_path / "beacon.sqlite"),
               str(tmp_path / "keks"), old_row_readers=LANGS)


def _migration(side, case, migrator, slot, store, old_row_readers=("cpp", "python")):
    side.activate()
    conn = side.connect(slot)
    for sql in STARTS[case]:
        conn.execute(sql.format(t="beacon_log_table", id=PK))
    conn.commit()
    conn.close()
    _ok(side.batch(migrator, [("migrate", "beacon_log", slot, "")], store),
        migrator + " migrate")

    cls = side.msgs["beacon_log"]

    def read_all(pks, readers):
        out = {}
        for lang in readers:
            res = side.batch(lang, [("read", "beacon_log", slot, str(pk)) for pk in pks], store)
            _ok(res, "{} reads after {} migrated".format(lang, migrator))
            out[lang] = [cls.FromString(bytes.fromhex(p)) for _, p in res]
        return out

    old = read_all([1], old_row_readers)
    assert all(v == old["cpp"] for v in old.values()), old
    want = {"rename_drop_add": ("north", 0), "retype": ("east", 42)}[case]
    assert (old["cpp"][0].label, old["cpp"][0].strength) == want

    # rows written after the migration (hidden columns bound, never NULL)
    rows = {}
    for pk, lang in ((2, "cpp"), (3, "python"), (4, "java")):
        m = cls(label="{}-row".format(lang), strength=pk * 10)
        setattr(m, PK, pk)
        setattr(m, "STATUS_" + HASH, "ok")
        rows[pk] = m
        _ok(side.batch(lang, [("write", "beacon_log", slot, m.SerializeToString().hex())],
                       store), lang + " write after migration")
    new = read_all(sorted(rows), LANGS)
    assert new["cpp"] == new["python"] == new["java"] == [rows[pk] for pk in sorted(rows)]


# -- PostgreSQL (opt-in) ---------------------------------------------------

# patient_vitals' phi heart_rate keeps DOUBLE PRECISION in the shared DDL and
# can't hold enc:v1: text (NEXT_SESSION item 26) -- strict so a fix shows.
_PHI_NUMERIC_ON_PG = "patient_vitals"


@pg_only
@pytest.mark.parametrize("writer", LANGS)
def test_pg_cross_read_write(writer, pg_side, pg_databases, tmp_path):
    names = [n for n in pg_side.tables if n != _PHI_NUMERIC_ON_PG]
    _matrix(pg_side, writer, _slot_factory(pg_side, tmp_path, pg_databases),
            str(tmp_path / "keks"), names)


@pg_only
@pytest.mark.xfail(strict=True,
                   reason="C++ FINDING (item 26): numeric phi column keeps its numeric PG type")
@pytest.mark.parametrize("writer", ("cpp", "python"))
def test_pg_phi_numeric_column(writer, pg_side, pg_databases, tmp_path):
    _matrix(pg_side, writer, _slot_factory(pg_side, tmp_path, pg_databases),
            str(tmp_path / "keks"), [_PHI_NUMERIC_ON_PG])


@pg_only
@pytest.mark.parametrize("migrator", ("cpp", "python"))
@pytest.mark.parametrize("case", ("rename_drop_add", "retype"))
def test_pg_migration_then_cross_read(case, migrator, pg_side, pg_databases, tmp_path):
    _migration(pg_side, case, migrator, pg_databases(), str(tmp_path / "keks"))


@pg_only
@_JAVA_NULL_TEXT
@pytest.mark.parametrize("migrator", ("cpp", "python"))
def test_pg_java_reads_pre_migration_row(migrator, pg_side, pg_databases, tmp_path):
    _migration(pg_side, "rename_drop_add", migrator, pg_databases(), str(tmp_path / "keks"),
               old_row_readers=LANGS)
