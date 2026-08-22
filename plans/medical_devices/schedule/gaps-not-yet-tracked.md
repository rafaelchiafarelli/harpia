# Gaps not yet assigned to any track

Added 2026-08-18, cross-referencing `README.md`'s "Known gaps" (current
harpia `dev` @ `0757180`) against every track in `foundation.md` and
`session-1` through `session-4`. Everything else on that list already maps
onto an existing track (True crash/interrupt recovery → Track I; no YAML
serialization → Track F; no multi-tier RBAC → Track C; C++-only generation
target → Track J). Doxygen generation is now scoped on its own —
`plans/doxygen-generation.md` — so it's dropped from this file. This one
still doesn't have a home yet:

---

## PostgreSQL on Windows — RESOLVED 2026-08-22

Was: only SQLite verified on the native-Windows generated-code path;
`soci[postgresql]` never added to either vcpkg manifest; nothing tested
against a real Postgres server from Windows. Session with native Windows
exec access closed it: `examples/consumer/vcpkg.json` now also requests
`soci[sqlite3,postgresql]` (matching `Assets/vcpkg.json`, which already had
it); `examples/consumer/CMakeLists.txt` gained a `USE_POSTGRES` option
(default OFF) that does `find_package(PostgreSQL REQUIRED)` before
`find_package(SOCI CONFIG REQUIRED)` — no hand-written alias needed here,
unlike `SOCI::SQLite3`/`SQLite3::SQLite3` (vcpkg's `libpq` port hooks
CMake's builtin `find_package(PostgreSQL)` directly via its own
`vcpkg-cmake-wrapper.cmake`). Built and linked on MSVC + vcpkg (protobuf,
grpc, soci, libpq all compiled from source), then run against a real
`postgres:16` container: `create_table`/`create`/`list`/`read` round-tripped
over a genuine `soci::postgresql` session, verified independently via
`psql` against the container. See `USAGE.md` §8/§12 and `Assets/CLAUDE.md`
for the detail. Track N's parity gate can now honestly compare
Windows-Postgres against Linux-Postgres variants.

---

## ZMQ CURVE Windows build-verification

This one *is* already tracked (see the 2026-08-18 update note on Track B
in `session-2-transport-and-access.md`) — listed here only so a scan of
this file catches it too. `Assets/vcpkg.json`'s `zeromq` dependency has
the `curve`+`sodium` features added; the `-DUSE_ZMQ_CURVE=ON` build path
has not been exercised on a native Windows host.
