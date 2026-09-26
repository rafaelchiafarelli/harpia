## `GrpcServer` over a `soci::connection_pool`

- **Depends on:** nothing.
- **Contract:** generated `grpc/grpc_server_bringup.h` gains constructors
  taking `::soci::connection_pool& pool` alongside the existing
  `::soci::session& db` ones (**additive**; existing callers and golden
  output for them unchanged). With a pool, each generated service handler
  borrows one session per RPC (`soci::session s(pool);`, RAII-returned) and
  never holds it across calls. The per-message `<name>_grpc.h` service class
  gets a matching pool-taking constructor. The pool size is the caller's choice
  (they construct the pool). harpia doesn't pick a number.
- **Why pool, not a mutex:** a mutex would serialize every RPC through one
  connection, which is exactly the bottleneck the load harness exists to
  expose. A pool is SOCI's own answer and works for SQLite and PostgreSQL.
  **Confirm with Rafael before implementing** if any other approach is
  preferred; this is the one generator design decision in the initiative.
- **Pre-work:** none.
- **Out of scope:** REST/SOAP (task 2), pool sizing guidance beyond a
  `USAGE.md` note.
- **Tests:** a new test drives 32 concurrent gRPC clients × 200 mixed CRUDL
  calls against a pooled server (SQLite file DB in the default suite, live
  PostgreSQL via `Docker/run_pg_tests.sh`): no crash, no lost or corrupted rows
  (final count and content checked). The same test against the old
  shared-session constructor is **not** added, because it would be flaky by
  nature. The race is documented in `Database/CLAUDE.md` instead. Goldens
  regenerated and reviewed.
