## Connection pool + per-request borrow (servers are multi-threaded from day one)

- **Depends on:** `py-database` tasks 2a, 3.
- **Why first:** every Python server in this epic runs handlers on many
  threads (`ThreadingHTTPServer`, the gRPC thread pool). The C++ target
  learned the hard way (`multi-system-reference` / `db-concurrency`) that
  one shared session is a race. `sqlite3` connections additionally refuse
  cross-thread use by default. So Python starts pooled. This mirrors the
  **design** of C++ `PooledSession` (db-concurrency 1a + 1b part 1), which
  at planning time was not yet on `dev`. Depend on the documented
  semantics, not on that code.
- **Contract:** `harpia_runtime/db/pool.py`:
  - `ConnectionPool(factory, size, borrow_timeout_s)` and
    `pool.borrow()` (a context manager yielding a connection).
  - Deadline on `time.monotonic()`, never wall clock: the WSL2 clock-step
    lesson from 1a.
  - Timeout → `PoolExhausted`. A dead connection is reconnected on borrow;
    if that fails → `PoolReconnectFailed`.
  - Rollback on exceptional exit; the connection is always given back.
  - A SQLite pool refuses `:memory:` (each connection would be its own
    empty DB): `ValueError` naming the fix.
  - File SQLite connections are opened with `PRAGMA journal_mode=WAL`,
    `busy_timeout`, and `check_same_thread=False`. That last one is safe
    because the pool guarantees exclusive borrow.
  - Postgres: `psycopg` connections. A `psycopg_pool` dependency is
    **not** added; one small pool serves both dialects.
- **Out of scope:** the servers that use it (tasks 2–4).
- **Tests:**
  - Unit tests: borrow/return, timeout → `PoolExhausted` within bound,
    rollback on exception, reconnect, `:memory:` refused.
  - Concurrency: 8 threads × 100 creates over a file-SQLite pool of 4
    gives an exact final count and no "database is locked".
  - A monotonic-deadline test: patch `time.time` to jump and assert the
    borrow still waits its full timeout.
