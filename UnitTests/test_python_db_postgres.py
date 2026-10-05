"""The generated Python DAOs on PostgreSQL through psycopg (python-target /
py-database task 3).

Opt-in, like ``test_stage8_pg.py``: skipped unless ``HARPIA_PG_DSN`` points
at a reachable server (and the Python toolchain is present). Run with::

    Docker/run_pg_tests.sh UnitTests/test_python_db_postgres.py

Generates the fixture with ``HARPIA_DB_BACKEND=postgresql`` and runs the
task 2a-2c round trips (scalar, embed/FK, every child-table shape) against
a fresh schema, which is dropped afterwards. Also checks that the dialect
came from ``DbBackend`` alone: ``%s`` placeholders, PostgreSQL DDL.
"""
import importlib
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests._java_gradle_helpers import generate  # noqa: E402

PG_DSN = os.environ.get("HARPIA_PG_DSN")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH

pytestmark = pytest.mark.skipif(
    not PG_DSN or not P.HAVE_PY or not P._importable("psycopg"),
    reason="needs HARPIA_PG_DSN + psycopg + the Python toolchain (opt-in live PG)")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return generate(tmp_path_factory.mktemp("py_pg"), lang="python",
                    db_backend="postgresql")


@pytest.fixture(scope="module")
def msgs(gen):
    return P.fixture_messages(P.py_root(gen))


@pytest.fixture()
def conn(gen):
    import psycopg
    schema = "harpia_py_" + uuid.uuid4().hex[:10]
    c = psycopg.connect(PG_DSN)
    c.execute('CREATE SCHEMA "{}"'.format(schema))
    c.execute('SET search_path TO "{}"'.format(schema))
    c.commit()
    yield c
    c.rollback()
    c.execute('DROP SCHEMA "{}" CASCADE'.format(schema))
    c.commit()
    c.close()


def _dao(name):
    mod = importlib.import_module("harpia_generated.db.{}_{}_dao".format(name, HASH))
    return getattr(mod, name + "_dao")


def _create_tables(dao_cls, conn, seen=None):
    """This DAO's tables and those of every DAO its FKs reach (users and
    top_users share one table name, so never create everything)."""
    from harpia_runtime.db import dao as rt
    seen = set() if seen is None else seen
    if dao_cls in seen:
        return
    seen.add(dao_cls)
    dao_cls(conn).create_table()
    for ref in [c.fk for c in dao_cls.COLUMNS] + [c.fk for c in dao_cls.CHILDREN]:
        if ref:
            _create_tables(rt.dao_class(ref), conn, seen)


def test_dialect_comes_from_the_backend(gen, msgs):
    users = _dao("users")
    assert "%s" in users.INSERT_SQL and "?" not in users.INSERT_SQL
    assert "dialect: ``postgresql``" in open(
        importlib.import_module(users.__module__).__file__).read()


# patient_vitals' phi `heart_rate` is a float column: the shared DDL keeps it
# DOUBLE PRECISION, which can't hold the enc:v1: text phi encryption stores
# (py-crypto-phi task 4). Same DDL + same bound text in C++ -> a C++ finding,
# logged in Initiatives/python-target/NEXT_SESSION.md; strict so a fix shows.
_PHI_NUMERIC_ON_PG = pytest.mark.xfail(
    strict=True, reason="C++ FINDING: numeric phi column keeps its numeric PG type")


@pytest.mark.parametrize("name", ["users", "beacon_log", "crew",
                                  pytest.param("patient_vitals", marks=_PHI_NUMERIC_ON_PG),
                                  "journey", "top_users", "outpost",
                                  "data", "telemetry", "shipment"])
def test_round_trip_on_postgres(name, msgs, conn):
    from UnitTests.test_py_db_dao import _populated, persisted_view
    cls, dao_cls = msgs[name], _dao(name)
    _create_tables(dao_cls, conn)
    dao = dao_cls(conn)
    rows = [_populated(cls, pk) for pk in (1, 2, 3)]
    for i, m in enumerate(rows):
        from UnitTests.test_py_db_dao import _unique_ids
        _unique_ids(m, [100000 * (i + 1)])
        setattr(m, PK, i + 1)
        assert dao.create(m)
    got = cls()
    assert dao.read(2, got)
    assert persisted_view(dao_cls, got) == persisted_view(dao_cls, rows[1])
    assert dao.update(rows[1]) and not dao.update(_populated(cls, 99))
    assert [getattr(m, PK) for m in dao.list(1, 1)] == [2]
    assert [getattr(m, PK) for m in dao.list(offset=1)] == [2, 3]
    assert len(dao.list()) == 3
    assert dao.remove(1) and not dao.remove(1)
    assert not dao.read(1, cls())


def test_migrate_on_postgres(msgs, conn):
    """task 5a on PostgreSQL: rename keeps data, stray dropped, TEXT strength
    retyped to integer (ALTER COLUMN .. TYPE), version stamped, idempotent."""
    table = "beacon_log_table"
    conn.execute('CREATE TABLE "{t}" ("{pk}" INTEGER PRIMARY KEY, "handle" TEXT, '
                 '"strength" TEXT, "legacy_note" TEXT)'.format(t=table, pk=PK))
    conn.execute("INSERT INTO \"{t}\" VALUES (1, 'north', '42', 'x')".format(t=table))
    conn.commit()
    mig = importlib.import_module("harpia_generated.migrate.beacon_log_{}_migrate".format(HASH))
    assert mig.migrate_beacon_log(conn)
    assert mig.migrate_beacon_log(conn)
    cols = dict(conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s", [table]).fetchall())
    assert set(cols) == set(mig.SPEC.current_columns)
    assert cols["strength"] == "integer"
    got = msgs["beacon_log"]()
    assert _dao("beacon_log")(conn).read(1, got)
    assert got.label == "north" and got.strength == 42
    assert conn.execute('SELECT "version" FROM "_harpia_schema_version"').fetchall() == [(HASH,)]


def test_migrate_child_tables_on_postgres(msgs, conn):
    """task 5b on PostgreSQL: child-table renames keep their rows, an orphan
    child table is reaped, the map key/value and the repeated-composed shape
    are evolved (ALTER COLUMN .. TYPE / ADD / DROP), idempotent."""
    t = "telemetry_table"
    for sql in [
        'CREATE TABLE "{t}" ("{pk}" INTEGER PRIMARY KEY, "label" TEXT)',
        "INSERT INTO \"{t}\" VALUES (1, 'dev')",
        'CREATE TABLE "{t}__old_notes" ("owner" INTEGER, "ordinal" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "ordinal"))',
        "INSERT INTO \"{t}__old_notes\" VALUES (1, 0, 'alpha'), (1, 1, 'beta')",
        'CREATE TABLE "{t}__old_flags" ("owner" INTEGER, "key" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "key"))',
        "INSERT INTO \"{t}__old_flags\" VALUES (1, -3, 'neg'), (1, 4, 'four')",
        'CREATE TABLE "{t}__gauges" ("owner" INTEGER, "key" INTEGER, '
        '"value" TEXT, PRIMARY KEY("owner", "key"))',
        "INSERT INTO \"{t}__gauges\" VALUES (1, 7, '42')",
        'CREATE TABLE "{t}__traces" ("owner" INTEGER, "ordinal" INTEGER, '
        '"kind" INTEGER, "note" TEXT, PRIMARY KEY("owner", "ordinal"))',
        "INSERT INTO \"{t}__traces\" VALUES (1, 0, 5, 'legacy')",
        'CREATE TABLE "{t}__gone" ("owner" INTEGER)',
    ]:
        conn.execute(sql.format(t=t, pk=PK))
    conn.commit()
    mig = importlib.import_module("harpia_generated.migrate.telemetry_{}_migrate".format(HASH))
    assert mig.migrate_telemetry(conn)
    assert mig.migrate_telemetry(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema()").fetchall()}
    assert {t + "__" + c for c in ("gauges", "flags", "samples", "notes", "traces")} <= tables
    assert not {n for n in tables if "__old_" in n or n.endswith("__gone")}

    def types(table):
        return dict(conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s", [table]).fetchall())

    assert (types(t + "__gauges")["key"], types(t + "__gauges")["value"]) == ("text", "integer")
    traces = types(t + "__traces")
    assert traces["kind"] == "text" and "weight" in traces and "note" not in traces
    got = msgs["telemetry"]()
    assert _dao("telemetry")(conn).read(1, got)
    assert list(got.notes) == ["alpha", "beta"]
    assert dict(got.flags) == {-3: "neg", 4: "four"}
    assert dict(got.gauges) == {"7": 42}
    assert [tr.kind for tr in got.traces] == ["5"]


def test_py_migration_ignores_other_schemas(msgs, conn):
    """cpp-pg-introspection-schema-DEFECT, Python engine: a same-named
    beacon_log_table (extra column, strength TEXT) and a
    telemetry_table__decoy_child in ANOTHER schema neither leak into this
    schema's migration nor get touched by it."""
    decoy = "harpia_decoy_" + uuid.uuid4().hex[:10]
    conn.execute('CREATE SCHEMA "{}"'.format(decoy))
    conn.execute('CREATE TABLE "{d}"."beacon_log_table" ("{pk}" INTEGER PRIMARY KEY, '
                 '"label" TEXT, "strength" TEXT, "decoy_only" TEXT)'.format(d=decoy, pk=PK))
    conn.execute('CREATE TABLE "{}"."telemetry_table__decoy_child" ("owner" INTEGER)'.format(decoy))
    conn.commit()
    try:
        for name in ("beacon_log", "telemetry"):
            mig = importlib.import_module(
                "harpia_generated.migrate.{}_{}_migrate".format(name, HASH))
            assert getattr(mig, "migrate_" + name)(conn)
            assert getattr(mig, "migrate_" + name)(conn)

        def cols(schema, table):
            return dict(conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s", [schema, table]).fetchall())
        here = conn.execute("SELECT current_schema()").fetchone()[0]
        assert "decoy_only" not in cols(here, "beacon_log_table")
        assert cols(here, "beacon_log_table")["strength"] == "integer"
        assert cols(decoy, "beacon_log_table")["decoy_only"] == "text"
        assert cols(decoy, "beacon_log_table")["strength"] == "text"
        assert cols(decoy, "telemetry_table__decoy_child")
    finally:
        conn.rollback()
        conn.execute('DROP SCHEMA "{}" CASCADE'.format(decoy))
        conn.commit()
