# station -- the DB server (C++, Windows target)

The only program in the reference system that owns a database. It runs the
generated, hardened gRPC services (mTLS required, RBAC, bearer sessions) over
a `soci::connection_pool`. See `../README.md` for the whole system.

```sh
# 1. generate (inside the harpia Docker image; output under the repo's
#    git-ignored build/). Pick the DB dialect station will use -- the
#    migrations are dialect-specific: postgresql here, or leave
#    HARPIA_DB_BACKEND out for SQLite. HARPIA_GEN_LANG=java also emits the
#    Java side handheld needs; C++ is always generated.
Docker/run.sh env HARPIA_DB_BACKEND=postgresql HARPIA_GEN_LANG=java \
    HARPIA_INPUT_FILE=HarpiaTest/app_example/multi_system/harpia/multi_system.harpia \
    HARPIA_INCLUDE_FOLDER=HarpiaTest/app_example/multi_system/harpia/Include \
    HARPIA_COMPLIANCE_CONFIG=HarpiaTest/app_example/multi_system/harpia/project.harpia.yaml \
    HARPIA_OUTPUT_DIR=build/ms_gen python3 main.py
# 2. build
cmake -S HarpiaTest/app_example/multi_system/station -B build/station -DHARPIA_GEN=$PWD/build/ms_gen
cmake --build build/station
# 3. run (PKI from Assets/cmake/mtls_provision.sh --clients-file ../harpia/clients.txt)
HARPIA_RBAC_MAP=pki/rbac_map.txt HARPIA_SESSION_KEY=<secret> \
  build/station/station --listen 0.0.0.0:50051 --db "host=127.0.0.1 dbname=ms user=ms" \
                        --pool 16 --certs pki
```

| Flag | Default | Meaning |
|---|---|---|
| `--db` | (required) | PostgreSQL conninfo, or `sqlite:<file>` (WAL + busy timeout; never `:memory:`) |
| `--listen` | `0.0.0.0:50051` | gRPC address |
| `--pool` | 16 | connections in the pool (keep under PostgreSQL `max_connections`) |
| `--certs` | `.` | directory with `ca.pem`, `server.pem`, `server_key.pem` |
| `--lease-timeout-ms` | 2000 | how long a call waits for a free connection (then `RESOURCE_EXHAUSTED`) |
| `--stats-every` | 10 | seconds between stats lines |

Stats line, every `--stats-every` seconds:

```
station: last 10s calls=1203 sessions=42 errors=0 (total calls=55120 errors=3)
```

`calls` = RPCs received, `errors` = RPCs answered with a non-OK status,
`sessions` = distinct bearer tokens presented in the window (tokens are
stateless, so "active" means "used recently"). Ctrl-C / SIGINT / SIGTERM shut
down cleanly (in-flight calls get 5 s).

## Why its own ServerBuilder

station registers the generated `<name>_service`s on its own
`grpc::ServerBuilder` (the `USAGE.md` section 7.5 alternative) instead of using
the generated `GrpcServer`, only to add a gRPC server interceptor for the stats
line (`GrpcServer` keeps its builder private). Everything security-relevant is
still the generated code: the RBAC + session gate inside each service,
`server_credentials()` (fail-safe: missing PEM files refuse to start), the
pooled borrowing, and `refuse_sqlite_memory_pool()`, which station calls itself.

## Windows notes (for the Windows verification session)

Platform-specific code, all behind `#ifdef _WIN32`:

- **Shutdown hook** (`station.cpp`): `SetConsoleCtrlHandler` on Windows, `std::signal(SIGINT/SIGTERM)` elsewhere. Both only set an atomic flag; the main loop does the shutdown.

Everything else is standard C++17 + gRPC + SOCI. The build:

- Uses `vcpkg.json` in this directory (manifest mode): `protobuf`, `grpc`, `cppzmq`, and `soci` with `sqlite3` + `postgresql`.
- On Windows, `../cmake/harpia_ms.cmake` regenerates the message and gRPC code from the generated `.proto` files with vcpkg's own protoc + `grpc_cpp_plugin`. The Docker-baked `*.pb.cc` don't compile against vcpkg's newer protobuf; the same reason as in `app_example/consumer`.
- Applies the vcpkg SOCI quirks described in `app_example/consumer/CMakeLists.txt` (the `SQLite3::SQLite3` alias).
