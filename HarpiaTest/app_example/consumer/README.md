# Consuming Harpia output — worked example

A **standalone project** that uses Harpia-generated code as a black box. It does
not depend on the Harpia repo — only on a project you generate with
`run_harpia.sh`, pointed at via `-DHARPIA_GEN`.

It exercises three generated layers for the `users` message:
- the **CRUDL DAO** (`harpia::db::users_dao` over a `soci::session`),
- the **JSON adapter** (`harpia::json::to_json`),
- the **REST bindings** (`harpia::rest::register_users` on a `crow::SimpleApp`).

## Run it

```sh
# 1. generate a project from a .harpia (the bundled HarpiaTest, SQLite backend)
./run_harpia.sh HarpiaTest /tmp/gen --no-build

# 2. build this consumer against that generated project
cmake -S HarpiaTest/app_example/consumer -B /tmp/consumer_build -DHARPIA_GEN=/tmp/gen
cmake --build /tmp/consumer_build

# 3. run
/tmp/consumer_build/consumer
```

Inside the toolchain image (no host deps needed):

```sh
docker/run.sh bash -c '
  HARPIA_OUTPUT_DIR=/tmp/gen python3 main.py &&
  cmake -S HarpiaTest/app_example/consumer -B /tmp/cb -DHARPIA_GEN=/tmp/gen &&
  cmake --build /tmp/cb && /tmp/cb/consumer'
```

Expected output:

```
rows in the table: 2
  #1  alice (wonderland)
  #2  bob (builder)
user #1 as JSON: {"IDC96f8fd7f45108efee5a8ecb43eab1da":1,"address":"wonderland","name":"alice"}
REST server started on http://127.0.0.1:<port>/api/v1/users
OK
```

## Windows

Verified end to end on MSVC (Visual Studio 2022) + vcpkg, including `-DUSE_TLS=ON`:

```
cmake -S examples\consumer -B build ^
    -A x64 -DCMAKE_TOOLCHAIN_FILE=C:\vcpkg\scripts\buildsystems\vcpkg.cmake ^
    -DHARPIA_GEN=<output_folder>
cmake --build build --config Release
build\Release\consumer.exe
```

`vcpkg.json` in this folder declares the needed ports (`protobuf`, `grpc`,
`soci[sqlite3]`, `openssl`); the toolchain file drives `vcpkg install`
automatically. See [USAGE.md §11](../../../USAGE.md#11-building-on-windows) for
what's behind the `if(WIN32)` branches in `CMakeLists.txt` and known gaps
(PostgreSQL and the Stage 14 test suite aren't verified there).

## Files
- [`src/main.cpp`](src/main.cpp) — the application: open a session → DAO → JSON → REST.
- [`CMakeLists.txt`](CMakeLists.txt) — how the generated headers, vendored Crow/asio/
  tinyxml2, protobuf and SOCI are wired into a build.

## TLS

Build with `-DUSE_TLS=ON` to serve the REST demo over HTTPS instead of plain
HTTP — CMake generates a self-signed cert at configure time and Crow's
`ssl_file()` (already in the vendored header, just gated behind
`CROW_ENABLE_SSL`) picks it up:

```sh
cmake -S HarpiaTest/app_example/consumer -B /tmp/cb_tls -DHARPIA_GEN=/tmp/gen -DUSE_TLS=ON
cmake --build /tmp/cb_tls
/tmp/cb_tls/consumer
```

Output is identical except the last line reads `https://127.0.0.1:<port>/api/v1/users`.
See [USAGE.md §9](../../../USAGE.md#9-enabling-tls-on-restsoapgrpc) for the gRPC
equivalent (`grpc::SslServerCredentials`, no extra linking needed).

## Notes
- Generated names are **md5-hash-qualified** (`users_<hash>_crudl.h`, accessor
  `id_<hash>()`); the hash is derived from your `.harpia` input. This example is
  pinned to HarpiaTest's hash — regenerate from your own input and update the
  includes/accessors accordingly.
- To target **PostgreSQL**, generate with `HARPIA_DB_BACKEND=postgresql`, include
  `<soci/postgresql/soci-postgresql.h>`, open the session with
  `::soci::postgresql`, and link `soci_postgresql` instead of `soci_sqlite3`
  (add `-I $(pg_config --includedir)`). The DAO/REST code is unchanged.
