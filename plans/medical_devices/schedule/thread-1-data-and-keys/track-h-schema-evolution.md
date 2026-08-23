# Track H — DB schema-evolution backlog

**Update (2026-08-18, current harpia `dev` @ `0757180`) — partially done,
scope narrowed:** RENAME/ADD/DROP/RETYPE for the *main* table are already
implemented (`renamed_from[<old>]` DSL modifier, additive ALTER,
implicit runtime-diff for drop, runtime-introspected type-mismatch
detection for retype) — don't re-plan or re-build these; see
`Database/CLAUDE.md`'s `MigrationAdapter.py` bullet. `migrate_<name>` also
now takes an optional caller-supplied
`std::function<void(::soci::session&)> data_transform` hook (runs after
add, before drop) for value-level transforms an automatic diff can't
express — directly relevant to Track A's `phi`-column reshaping later
(see `USAGE.md` §6).

**What's still genuinely missing, and the real scope of the three
sessions below:** `MigrationAdapter._render()` only calls `analyze()`,
which covers the main table's own columns — it never calls
`map_fields()` or `repeated_fields()`, so migration never touches a
message's child tables. A live database with a stale child-table column
set is never brought up to date by `migrate_<name>` today; only a fresh
`create_table()` gets the current child-table shape.

## Receives (must be done before this track starts)

- **Nothing, structurally.** This is pre-existing debt, independent of
  the compliance work Foundation (F1–F5) introduces — it does not depend
  on any of F1–F5. It's grouped into this thread only for scheduling
  (paired with Track O so the thread can start with two concurrent
  sessions/repos) — not a technical dependency.

## Gives (what "done" means here, consumed by whom)

- Child-table (map/repeated-scalar/repeated-composed) schema migration
  support wired into `migrate_<table>()`, matching the main-table
  rename/add/drop/retype machinery that already exists.
- **Consumed by:** Track A (`track-a-db-encryption.md` lists this track
  as a precondition) — a `phi` field living in a child table needs this
  machinery in place before Track A's encryption/reshaping work on that
  field can safely evolve across schema versions.

## Files this track touches

- `Database/MigrationAdapter.py` — specifically its `_render()` method,
  and the calls it needs to add to `map_fields()`/`repeated_fields()`
  (currently calls only `analyze()`). Named explicitly in the plan text
  this file is built from.
- Broader area: `Database/` (per `harpia_medical_master_plan.md` §2's
  track table). **Flag:** no other specific filenames beyond
  `MigrationAdapter.py` are named in the plan docs — not guessing
  further than that.

---

## Session H.1 — Repeated-scalar child-table migration

- **Depends on:** none (see Receives above).
- **Deliverable:** wire `MigrationAdapter._render()` to also call
  `repeated_fields()` (today it only calls `analyze()`); implement
  rename/add/drop/retype for repeated-scalar child tables.
- **Guarantees:** `migrate_<table>()` correctly handles repeated-scalar
  child-table schema changes without data loss outside what the
  transform itself specifies.
- **Tests:**
  - Unit: repeated-scalar child table migrated in isolation, each
    transform type (rename/add/drop/retype).
  - Integration: old DB snapshot + new schema version with a
    repeated-scalar field → migrate → verify data integrity.

## Session H.2 — Map child-table migration

- **Depends on:** H.1 merged (reuses its `_render()` wiring pattern —
  do H.1 first even though the two don't share code paths).
- **Deliverable:** wire `MigrationAdapter._render()` to also call
  `map_fields()`; implement rename/add/drop/retype for map child tables.
- **Guarantees:** same as H.1, for map child tables.
- **Tests:** same shape as H.1 (unit per transform type, integration
  round trip), for map fields.

## Session H.3 — Repeated-composed child-table migration

- **Depends on:** H.1 merged (`repeated_fields()` wiring already in
  place, reused here — H.2 not required first, H.2 and H.3 could swap
  order).
- **Deliverable:** implement rename/add/drop/retype for
  repeated-composed child tables.
- **Guarantees:** same as H.1, for repeated-composed child tables.
- **Tests:** same shape as H.1, for repeated-composed fields.
- **Acceptance gate (covers H.1–H.3 together):** existing
  additive-migration and `data_transform`-hook tests unchanged.

## Watch for

- H.2 and H.3 both build on H.1's `_render()` wiring change — merge H.1
  first regardless of which of H.2/H.3 you pick up next.
