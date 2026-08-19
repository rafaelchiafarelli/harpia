# Plans index

Scoping/planning docs for work that's bigger than a single session. Each doc
below is either a **live plan** (being executed, slice by slice) or a
**scoping doc** (recommendation + sizing, not yet started). `README.md`'s
top-level "Known gaps" section stays the live, authoritative list of
implemented-vs-missing features; this index is for the *why/how* behind the
bigger unimplemented pieces, and for backlog items that don't have their own
doc yet.

| Doc | Status |
|---|---|
| [postgres-migration.md](postgres-migration.md) | Done — SOCI + PostgreSQL backend shipped (db-agnostic slices 0-6) |
| [multi-language-targets.md](multi-language-targets.md) | Scoped, not started — Python recommended as target #2 |
| [medical_devices/](medical_devices/harpia_medical_master_plan.md) | Scoped, not started — compliance profile for regulated deployments |
| [message-versioning.md](message-versioning.md) | Scoped, not started — stable wire field numbers + version handshake so mismatched-schema peers degrade instead of silently corrupting data |

## Backlog

Open items not yet big enough for their own scoping doc. Moved here from
`NEXT_SESSION.md`, which is a short-lived handoff note (what just happened,
what to check first) rather than a place to accumulate a durable backlog.
Add to this list piecemeal as items get scoped or come up — no need to do it
all at once.

- **PostgreSQL backend on Windows** — small, scoped 2026-08-19. The
  generator side is already done and Windows-independent:
  `HARPIA_DB_BACKEND=postgresql` (SQL dialect, DAO templates, migration
  adapter) is fully implemented and tested today via
  `tests/test_stage8_pg.py`, including an opt-in live-server integration
  test. The gap is purely how the two platforms link SOCI's PostgreSQL
  backend:
  - **Linux** already has everything installed (Dockerfile's
    `libsoci-postgresql4.0` + `libpq-dev`) — apt's SOCI has no CMake
    package, just bare `.so` names, so it's `soci_postgresql` next to
    `soci_core`, same shape as `soci_sqlite3` today.
  - **Windows** — `Assets/vcpkg.json` only requests `soci[sqlite3]`; add
    `postgresql` to that feature list. vcpkg's `soci` port exports one
    umbrella CMake target (`SOCI::SOCI`) that links every installed
    backend feature, so the existing Windows CMake code (three copies:
    `examples/consumer/CMakeLists.txt`,
    `tests/golden/gen_tests/CMakeLists.txt`, `TestAdapter.py`'s generated
    CMake) should pick up postgres with no changes — *if* vcpkg's `libpq`
    port doesn't have an
    analogous CONFIG-target quirk to the one `sqlite3` already needed a
    hand-written alias workaround for (`unofficial-sqlite3` →
    `SQLite3::SQLite3`, present in all three files). That can only be
    confirmed with a real vcpkg install + build on Windows, not by reading
    code.
  - **Bonus finding, not Windows-specific:** none of those three CMake
    templates actually branch on `HARPIA_DB_BACKEND` today — they
    hardcode sqlite3 regardless of which backend Python generated
    against. Only `test_stage8_pg.py`'s own hand-rolled g++ line links
    postgres. Wiring a `HARPIA_DB_BACKEND`-driven link choice into the
    shared templates fixes this on *both* platforms at once and is a
    prerequisite for the demo/Stage-14-ctest paths to ever exercise
    Postgres through the normal build, independent of Windows.
- **True crash/interrupt recovery** (resume a *killed mid-run* generate) —
  the sha256-registry/marker half of `harpia.architecture.md`'s "continuable
  process" that the write-if-different work explicitly did not attempt.
  Still just spec text, no design started.
- **Python as language #2** — see `multi-language-targets.md` for the scoped
  recommendation. Multi-session sized, don't start as a "quick session."
- **Smaller/unscoped:** no YAML serialization, no Doxygen generation, no
  multi-tier RBAC (single flat credential everywhere).
