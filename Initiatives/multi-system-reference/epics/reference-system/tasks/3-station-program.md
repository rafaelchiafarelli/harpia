## `station`: the Windows DB server (C++)

- **Depends on:** tasks 1, 2; epic `db-concurrency` tasks 1a + 1b.
- **Contract:** `HarpiaTest/app_example/multi_system/station/`: a C++ program
  (CMake `-DHARPIA_GEN=<path>`, same shape as `app_example/consumer`, plus a
  `vcpkg.json` for Windows) that:
  - opens a `soci::connection_pool` (size from `--pool N`, default 16) on
    PostgreSQL (`--db "<conninfo>"`) or SQLite (`--db sqlite:<file>`, for quick
    local runs),
  - runs the generated migrations,
  - starts the generated hardened `GrpcServer` on `--listen host:port` with the
    pool, `HARPIA_RBAC_MAP` + `HARPIA_SESSION_KEY` from env,
  - shuts down cleanly on SIGINT/Ctrl-C (Windows console handler included),
  - prints one line per 10s: calls served, active sessions, errors.
- **Pre-work:** none.
- **Out of scope:** any client logic; actual Windows verification (epic 5).
  The code must not use POSIX-only APIs outside `#ifdef`, and each such spot
  is listed in the README for the Windows session.
- **Tests:** builds and runs in Docker against the task-1 PKI; a C++ smoke
  client (the test's own, not `edge`) creates and reads a `reading` over mTLS.
