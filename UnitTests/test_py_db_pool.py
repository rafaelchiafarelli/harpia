"""python-target / py-transports-http task 1: ``harpia_runtime.db.pool``.

Image-gated, generated project:
- borrow/return accounting; a held pool raises ``PoolExhausted`` after the
  timeout (not before, not long after); a waiter gets the connection as soon
  as it is returned;
- exceptional exit rolls back and still returns the connection;
- a dead (closed) idle connection is replaced on borrow; a factory that then
  fails gives ``PoolReconnectFailed`` and the slot is not leaked;
- ``:memory:`` (and URI memory forms) refused with ``ValueError``; file
  connections use WAL + ``busy_timeout``;
- 8 threads × 100 ``users_dao.create`` through a file-SQLite pool of 4 end
  with exactly 800 rows and no error;
- the deadline is monotonic: ``time.time`` jumping by hours doesn't cut the
  wait short.
"""
import importlib
import os
import sqlite3
import sys
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_pool"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture()
def pool_mod(gen):
    return importlib.import_module("harpia_runtime.db.pool")


def test_borrow_return_and_exhaustion(pool_mod, tmp_path):
    pool = pool_mod.sqlite_pool(str(tmp_path / "a.db"), size=1, borrow_timeout_s=0.3)
    with pool.borrow() as conn:
        assert pool.in_use() == 1
        conn.execute("CREATE TABLE t (x INTEGER)")
        t0 = time.monotonic()
        with pytest.raises(pool_mod.PoolExhausted):
            with pool.borrow():
                pass
        assert 0.25 <= time.monotonic() - t0 < 2.0
    assert pool.in_use() == 0
    got = []

    def waiter():
        with pool.borrow() as c:
            got.append(c)
    holder = pool.borrow()
    first = holder.__enter__()
    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.1)
    holder.__exit__(None, None, None)
    t.join(2)
    assert got == [first]  # handed over once returned


def test_rollback_on_exception(pool_mod, tmp_path):
    pool = pool_mod.sqlite_pool(str(tmp_path / "b.db"), size=1)
    with pool.borrow() as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    with pytest.raises(RuntimeError):
        with pool.borrow() as conn:
            conn.execute("INSERT INTO t VALUES (1)")
            raise RuntimeError("handler failed")
    with pool.borrow() as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    assert pool.in_use() == 0


def test_reconnect_and_reconnect_failure(pool_mod, tmp_path):
    made = []

    def factory():
        if len(made) >= 2:
            raise sqlite3.OperationalError("database unreachable")
        made.append(sqlite3.connect(str(tmp_path / "c.db"), check_same_thread=False))
        return made[-1]
    pool = pool_mod.ConnectionPool(factory, 1, 0.5)
    with pool.borrow() as c1:
        pass
    c1.close()  # dies while idle
    with pool.borrow() as c2:
        assert c2 is not c1 and c2.execute("SELECT 1").fetchone() == (1,)
    c2.close()
    with pytest.raises(pool_mod.PoolReconnectFailed):
        with pool.borrow():
            pass
    assert pool.in_use() == 0  # the slot came back


@pytest.mark.parametrize("path", [":memory:", "", "file::memory:?cache=shared",
                                  "file:x?mode=memory"])
def test_memory_refused(pool_mod, path):
    with pytest.raises(ValueError, match="database file"):
        pool_mod.sqlite_pool(path)


def test_wal_and_busy_timeout(pool_mod, tmp_path):
    pool = pool_mod.sqlite_pool(str(tmp_path / "d.db"), busy_timeout_ms=4321)
    with pool.borrow() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 4321


def test_eight_threads_through_a_pool_of_four(pool_mod, gen, tmp_path):
    users = importlib.import_module("harpia_generated.db.users_{}_dao".format(HASH))
    # busy_timeout above the 5 s default: SQLite's busy handler is unfair and
    # fsync is slow on this WSL2/Docker filesystem, so one writer can starve
    # past 5 s under this contention (seen once in ~20 runs); the default
    # stays 5000 ms like C++'s kDefaultSqliteBusyTimeoutMs.
    pool = pool_mod.sqlite_pool(str(tmp_path / "e.db"), size=4, borrow_timeout_s=30,
                                busy_timeout_ms=20000)
    with pool.borrow() as conn:
        users.users_dao(conn).create_table()
    errors = []

    def worker(t):
        try:
            for i in range(100):
                m = users.users()
                setattr(m, PK, t * 1000 + i + 1)
                m.name = "u"
                with pool.borrow() as conn:
                    users.users_dao(conn).create(m)
        except Exception as e:  # pragma: no cover - reported below
            errors.append(repr(e))
    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with pool.borrow() as conn:
        assert conn.execute('SELECT COUNT(*) FROM "user_table"').fetchone()[0] == 800


def test_deadline_is_monotonic(pool_mod, tmp_path, monkeypatch):
    pool = pool_mod.sqlite_pool(str(tmp_path / "f.db"), size=1, borrow_timeout_s=0.4)
    real = time.time
    jumps = iter(range(1, 10**6))
    monkeypatch.setattr(time, "time", lambda: real() + 3600 * next(jumps))
    with pool.borrow():
        t0 = time.monotonic()
        with pytest.raises(pool_mod.PoolExhausted):
            with pool.borrow():
                pass
        assert time.monotonic() - t0 >= 0.38
