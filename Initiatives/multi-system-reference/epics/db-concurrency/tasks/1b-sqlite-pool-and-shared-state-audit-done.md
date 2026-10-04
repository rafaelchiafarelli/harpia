## SQLite under a pool + thread-safety audit of other shared server state

Split from the original task 1 on 2026-09-26 (see 1a).

- **Depends on:** 1a.
- **Contract, part 1: SQLite under a pool.**
  - **`:memory:` + pool is refused, not silently wrong.** Each pooled
    `:memory:` connection is its own empty database. The pooled `GrpcServer`
    constructor detects a SQLite `:memory:` connection string and throws
    (`std::invalid_argument`, message naming the fix: a file path, or the
    single-session constructor). The single-session constructor keeps
    accepting `:memory:` unchanged, since existing tests depend on it.
  - **File SQLite is usable concurrently.** A generated helper that opens a
    SQLite pool sets `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=<ms>`
    on every connection, so concurrent writers wait instead of failing with
    "database is locked". Writes are still serialized by SQLite itself, which
    is documented as the reason PostgreSQL is the load target.
- **Contract, part 2: audit of other shared state.** gRPC already runs
  handlers on many threads, so anything a handler touches besides the DB
  session is already shared. Audit each of these and either prove it
  thread-safe (a TSan test) or make it so. This task must not expand into a
  redesign:
  - `AuditSink` (`Compliance/runtime/harpia_audit_sink.h`) and
    `default_audit_sink()`,
  - `KeyProvider` implementations used by `phi` DAOs (local, KMS mock),
  - `harpia_session.h` revocation-list re-read (`HARPIA_SESSION_REVOCATIONS`),
  - `harpia_rbac.h` map loading (`HARPIA_RBAC_MAP`, read once at startup),
  - event channels: already TSan-clean (`test_events_callbacks.py`), so only
    confirm they're still covered.
  Findings go in the relevant module `CLAUDE.md`. If any component needs
  more than a local lock to fix, **stop and flag it** as its own task and
  don't absorb it here.
- **Pre-work:** none.
- **Out of scope:** PostgreSQL behavior (1a), REST/SOAP (task 2).
- **Tests:**
  - Pooled constructor + `:memory:` throws.
  - A file-SQLite pool of 4 with 8 concurrent writers × 100 creates: no
    "database is locked" error, and the final count is exact.
  - A TSan build of the 1a concurrency test (against file SQLite, so it runs
    in the default suite) is race-free, covering handlers, RBAC gate, session
    verification and the `phi` audit path.
