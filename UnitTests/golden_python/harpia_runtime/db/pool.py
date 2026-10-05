"""A small DB-API connection pool with per-request borrow (the Python side
of the C++ ``harpia::db::PooledSession`` design, ``Database/runtime/harpia_db_pool.h``).

Hand-written, copied into a generated project as ``harpia_runtime.db.pool``.
Generated servers are multi-threaded, so each request borrows one
connection for its whole duration and gives it back::

    pool = sqlite_pool("app.db", size=4)
    with pool.borrow() as conn:
        users_dao(conn).read(1, msg)

- At most ``size`` connections; a borrow waits up to ``borrow_timeout_s``
  for a free one, then raises :class:`PoolExhausted`. The deadline uses
  :func:`time.monotonic`, never the wall clock, so a clock step can't cut
  the wait short.
- A connection that fails a liveness ping is replaced on borrow; if that
  fails too, :class:`PoolReconnectFailed`.
- Exceptional exit from ``borrow()`` rolls the connection back. The
  connection always goes back to the pool (or, if the rollback itself
  fails, is discarded and replaced on a later borrow).
- :func:`sqlite_pool` refuses an in-memory database (each connection would
  be its own empty database) and opens file databases with WAL,
  ``busy_timeout`` and ``check_same_thread=False`` (safe: a borrow is
  exclusive). :func:`postgres_pool` uses plain ``psycopg`` connections -- one
  small pool for both dialects, no ``psycopg_pool`` dependency.
"""
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from harpia_runtime.db.dao import Connection


class PoolExhausted(Exception):
    """No connection became free within the borrow timeout."""


class PoolReconnectFailed(Exception):
    """A dead connection could not be replaced."""


def _alive(conn: Connection) -> bool:
    try:
        conn.cursor().execute("SELECT 1")
        conn.rollback()  # don't leave the ping's transaction open (psycopg)
    except Exception:
        return False
    return True


def _close(conn: Connection) -> None:
    try:
        conn.close()  # type: ignore[attr-defined]
    except Exception:
        pass


class ConnectionPool:
    """At most ``size`` connections made by ``factory``, borrowed one per
    request. Thread-safe."""

    def __init__(self, factory: Callable[[], Connection], size: int,
                 borrow_timeout_s: float = 5.0,
                 is_alive: Callable[[Connection], bool] = _alive) -> None:
        if size < 1:
            raise ValueError("pool size must be at least 1")
        self._factory = factory
        self._size = size
        self._timeout = borrow_timeout_s
        self._is_alive = is_alive
        self._cond = threading.Condition()
        self._idle: list[Connection] = []
        self._out = 0  # connections currently borrowed
        self._made = 0  # connections that exist (idle + borrowed)

    @property
    def size(self) -> int:
        """The maximum number of connections."""
        return self._size

    def in_use(self) -> int:
        """Connections currently borrowed."""
        with self._cond:
            return self._out

    def _take(self) -> Connection | None:
        """Wait for a slot; an idle connection, or ``None`` to make one."""
        deadline = time.monotonic() + self._timeout
        with self._cond:
            while self._out >= self._size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolExhausted(
                        f"no database connection free within {self._timeout:g} s "
                        f"(pool size {self._size})")
                self._cond.wait(remaining)
            self._out += 1
            if self._idle:
                return self._idle.pop()
            self._made += 1
            return None

    def _give_back(self, conn: Connection | None) -> None:
        with self._cond:
            self._out -= 1
            if conn is None:
                self._made -= 1
            else:
                self._idle.append(conn)
            self._cond.notify()

    @contextmanager
    def borrow(self) -> Iterator[Connection]:
        """Borrow one connection for the ``with`` block (see the module doc)."""
        conn = self._take()
        try:
            if conn is not None and not self._is_alive(conn):
                _close(conn)
                conn = None
            if conn is None:
                try:
                    conn = self._factory()
                except Exception as e:
                    raise PoolReconnectFailed(
                        f"cannot open a database connection: {e}") from e
        except BaseException:
            self._give_back(None)
            raise
        try:
            yield conn
        except BaseException:
            try:
                conn.rollback()
            except Exception:
                _close(conn)
                self._give_back(None)
                raise
            self._give_back(conn)
            raise
        self._give_back(conn)

    def close(self) -> None:
        """Close every idle connection (borrowed ones close on return)."""
        with self._cond:
            idle, self._idle = self._idle, []
            self._made -= len(idle)
        for conn in idle:
            _close(conn)


def _is_memory(path: str) -> bool:
    p = path.strip()
    return p in ("", ":memory:") or p.startswith("file::memory:") or "mode=memory" in p


def sqlite_pool(path: str, size: int = 4, borrow_timeout_s: float = 5.0,
                busy_timeout_ms: int = 5000) -> ConnectionPool:
    """A pool over a SQLite **file** (WAL, ``busy_timeout``)."""
    if _is_memory(path):
        raise ValueError(
            f"a SQLite pool can't use {path!r}: every pooled connection would be its "
            "own empty in-memory database. Use a database file path.")

    def connect() -> Connection:
        conn = sqlite3.connect(path, timeout=busy_timeout_ms / 1000.0,
                               check_same_thread=False, uri=path.startswith("file:"))
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(mode).lower() != "wal":  # as C++ open_sqlite_pool
            conn.close()
            raise sqlite3.OperationalError(
                f"could not enable WAL journaling on {path!r} "
                f"(journal_mode is {mode!r})")
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        return conn

    return ConnectionPool(connect, size, borrow_timeout_s)


def postgres_pool(dsn: str, size: int = 4,
                  borrow_timeout_s: float = 5.0) -> ConnectionPool:
    """A pool of ``psycopg`` connections to ``dsn``."""

    def connect() -> Connection:
        import psycopg  # the generated project's optional `postgres` extra
        conn: Any = psycopg.connect(dsn)
        return conn  # type: ignore[no-any-return]

    return ConnectionPool(connect, size, borrow_timeout_s)
