## `GrpcServer` over a `soci::connection_pool`: safe borrowing

Split from the original task 1 on 2026-09-26, after Rafael reviewed the pool's
weaknesses. 1a is the pool and the per-call borrowing discipline; 1b is the
SQLite-specific behavior and the audit of other shared state.

- **Depends on:** nothing.
- **Contract:** generated `grpc/grpc_server_bringup.h` and the per-message
  `<name>_grpc.h` service classes gain constructors taking
  `::soci::connection_pool&` alongside the existing `::soci::session&` ones
  (**additive**; existing callers and their golden output unchanged). With a
  pool, every generated RPC handler goes through one generated RAII helper
  (`harpia::grpc_transport::PooledSession`, in a copied runtime header) that
  fixes the five rules below. The handlers never call `lease()` themselves.
  1. **Borrow with a deadline, never block forever.** `try_lease(pos,
     timeout_ms)`. On timeout the RPC returns `RESOURCE_EXHAUSTED` with the
     detail `"db pool exhausted"`. The timeout is a `GrpcServer` constructor
     argument with a default (e.g. 2000 ms) and no hidden env var.
  2. **Exactly one borrow per RPC.** The handler borrows once and passes that
     `soci::session&` down to every DAO call it makes (child tables, FK
     reads, migrations of the call included). A second borrow while one is
     held is a bug that can deadlock at saturation, so the helper asserts
     against it in debug builds (thread-local "already holding" flag).
  3. **Reconnect on borrow.** If `!is_connected()` on the borrowed session,
     `reconnect()` once. If that fails, return `UNAVAILABLE`
     (`"db reconnect failed"`) and give the slot back.
  4. **Clean state on return.** If the handler exits (normally or by
     exception) with a transaction open, the helper rolls it back before
     `give_back()`. A connection never returns to the pool mid-transaction.
  5. **Always give back.** RAII: exceptions, early returns and error statuses
     all return the slot.
  Pool size is the caller's choice (they construct and open the pool).
  `USAGE.md` gets a sizing note: stay under PostgreSQL `max_connections`
  (default 100) minus admin headroom, and each PostgreSQL connection is a
  server process (heavier on Windows). Tens of connections serve hundreds of
  clients when calls are short, and PgBouncer is the answer beyond that.
- **Pre-work:** none.
- **Out of scope:** SQLite behavior under a pool and other shared state (1b);
  REST/SOAP (task 2).
- **Tests:**
  - Concurrency: 32 concurrent gRPC clients × 200 mixed CRUDL calls against
    a pooled server on live PostgreSQL (the `Docker/run_pg_tests.sh`
    pattern). No crash, no lost or corrupted rows (final count and content
    checked).
  - Exhaustion: pool size 2, handlers slowed by a test hook, 10 concurrent
    calls. Some get `RESOURCE_EXHAUSTED` within about the timeout, none hang
    past the client deadline, and the server keeps serving afterwards.
  - Reconnect: kill the server-side backend of a pooled connection
    (`pg_terminate_backend`). The next call on that slot succeeds via
    reconnect.
  - Rollback: a test hook throws mid-transaction, then the next borrower of
    that slot sees no open transaction and no uncommitted row.
  - Leak: after all of the above, every slot is leasable again (pool fully
    returned).
  - Goldens regenerated and reviewed. The old shared-session race is
    documented in `Database/CLAUDE.md` but not tested (flaky by nature).
