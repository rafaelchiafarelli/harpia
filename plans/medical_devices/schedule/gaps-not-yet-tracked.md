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

## PostgreSQL on Windows

Only SQLite is verified on the native-Windows generated-code path (see
`USAGE.md` §12, "Known gaps on Windows"); `soci[postgresql]` was never
added to either vcpkg manifest (`Assets/vcpkg.json`,
`examples/consumer/vcpkg.json`), and nothing has been tested against a
real Postgres server from Windows.

Worth flagging explicitly to whoever owns Session 1 (Track A/K, DB
field-level encryption + segregation) and Session 4 (Track N's
feature-parity diff): if any jurisdiction build variant is expected to run
on Windows **and** use Postgres (rather than SQLite) as its backend — a
plausible combination for a hospital-integrated deployment — this gap sits
directly underneath that work and should be resolved before Track N's
parity gate can honestly compare Windows-Postgres against Linux-Postgres
variants.

**Scope, if picked up:** add `soci[postgresql]` (+ its `libpq` dependency)
to both vcpkg manifests; build-verify (needs native Windows exec access —
this file's authoring session didn't have it, see the Track B update in
`session-2-transport-and-access.md` for the same limitation hit there).

---

## ZMQ CURVE Windows build-verification

This one *is* already tracked (see the 2026-08-18 update note on Track B
in `session-2-transport-and-access.md`) — listed here only so a scan of
this file catches it too. `Assets/vcpkg.json`'s `zeromq` dependency has
the `curve`+`sodium` features added; the `-DUSE_ZMQ_CURVE=ON` build path
has not been exercised on a native Windows host.
