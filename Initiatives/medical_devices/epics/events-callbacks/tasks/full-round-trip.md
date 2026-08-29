## `AuditSink` hook on `OnChange` + full round-trip

- **Depends on:** task 1 + task 2 merged (both done); F3's `AuditSink`
  (`Compliance/runtime/harpia_audit_sink.h`, present on `dev`).

### Contract

The `AuditSink` hook fires in **two places** (Rafael's call — widest
coverage), each a value-free `record()` (Rule 5: names/ids only):

1. **`EventChannel<T>` (`Callback/runtime/harpia_event_cache.h`).** The
   channel gains: an `AuditSink*` defaulting to
   `&::harpia::compliance::default_audit_sink()`, a
   `set_audit_sink(AuditSink&)` (mutex-guarded — call once at startup,
   since `<name>_channel()` is a zero-arg function-local static), and two
   `std::string`s baked into the generated singleton by `CallbackAdapter`:
   `audit_subject_` (the message's `tableName` or name) and
   `audit_phi_fields_` (comma-joined `phi` field names; **empty ⇒ the
   channel carries no phi and never audits**).
   - `publish()` — when `audit_phi_fields_` is non-empty — records one
     `("phi_event_dispatch", audit_subject_, audit_phi_fields_)` on the
     calling thread, before the dispatch thread is spawned (deterministic;
     fires regardless of subscriber count).
   - the task-2 swallowed-callback `catch (...)` now also records
     `("event_callback_exception", audit_subject_ or "<event>", "")` — the
     `AuditSink*` captured under the lock at `publish()` time and passed
     into the dispatch thread, so `set_audit_sink()` can't race it.
   - ctor: `EventChannel(CacheMode, std::string subject = "",
     std::string phi_fields = "")` — new params defaulted so hand-written
     `EventChannel<int> c(CacheMode::Cached)` still compiles.
   - `harpia_event_cache.h` `#include "harpia_audit_sink.h"` (same-dir);
     `CallbackAdapter` copies `Compliance/runtime/harpia_audit_sink.h`
     (`Compliance.audit_common.AUDIT_SINK_RUNTIME_SRC`) into
     `generated/cpp/events/` alongside the cache runtime.

2. **The CRUDL DAO (`Database/CrudlAdapter.py` + `crudl.h.tmpl`).** A
   message that is **both `event` and `phi`-bearing** gets one extra
   `audit_.record("phi_event_onchange", "<table>", "<phi cols>")`
   immediately after the existing `<name>_channel().publish(msg)` call in
   `create()` and `update()` — reusing the DAO's existing `AuditSink&`
   member (db-encryption epic). Distinct op name from the channel's
   `phi_event_dispatch`: `phi_event_onchange` = "a persisted phi change
   was published to the event bus". New empty-placeholder
   (`{event_audit_create}` / `{event_audit_update}`), so a non-phi event
   DAO and a phi-non-event DAO are byte-identical.

**Generated-output / golden impact:** `golden/events/*` (every wrapper
gains the two ctor string args; `harpia_audit_sink.h` now sits in
`generated/cpp/events/` but is not snapshotted) and
`golden/db/alarm_event_*_crudl.h` (the one event+phi fixture). Nothing
else moves.

### `ComplianceReport/` note

`ComplianceReport/` does not exist on this `dev`-based branch (it is the
process-artifacts epic's module, on `origin/epics`). Follow the
db-encryption / critical-delivery precedent: add
`Initiatives/medical_devices/epics/process-artifacts/tasks/events-callbacks-phi-audit-note.md`
(a cross-epic folder write, pre-approved) — a stub task describing the
paragraph process-artifacts must file into `ComplianceReport/`: the two
new operation strings (`phi_event_dispatch`, `phi_event_onchange`), that
they are value-free, and that they mark PHI crossing the persistence
boundary onto the in-process event bus.

### Pre-work

None. `alarm_event` (`critical event message` + `phi string patient_id` +
`alarm_event_table`, already in `HarpiaTest/Include/file3.harpia`) is the
event+phi fixture the integration test drives — no new fixture, so no new
proto/zmq/sidecar golden.

### Tests — extend `UnitTests/test_events_callbacks.py`

- **Structural:** `alarm_event_*_events.h` passes the phi subject
  (`alarm_event_table`) + fields (`patient_id`) into its `EventChannel`
  ctor; `bed_state` / `pump_tick` / `data` / `users` (non-phi event
  messages) pass two empty strings; `harpia_audit_sink.h` is copied into
  `events/`. `alarm_event_*_crudl.h` has `phi_event_onchange` right after
  the `publish(` in `create` and `update`, and nowhere in
  `read`/`list`/`remove`; `data_*_crudl.h` (event, no phi) has `publish(`
  but no `phi_event_onchange`.
- **Runtime (g++):** a counting `AuditSink` subclass — a phi channel's
  `publish()` records exactly one `phi_event_dispatch` (even with zero
  subscribers); a non-phi channel records none; a throwing callback yields
  one `event_callback_exception`; `set_audit_sink()` retargets subsequent
  records. (Re-verify TSan-clean with the sink under contention.)
- **Integration (protoc + g++ + pkg-config gated, `test_stage8_db.py`
  harness shape):** generate → `ProtoCompiler` → compile a driver that
  opens an in-memory SOCI/sqlite session, constructs
  `harpia::db::alarm_event_dao dao(db, default_key_provider(), sink)`,
  `alarm_event_channel().set_audit_sink(sink)`, subscribes to
  `alarm_event_channel()`, `dao.create(msg)` — then asserts: the
  subscriber callback fires (bounded wait) with `patient_id` /
  `alarm_type` / `severity` matching what was written, and `sink` saw
  `phi_create` **and** `phi_event_onchange` (DAO) **and**
  `phi_event_dispatch` (channel). This is the epic's headline round-trip.

### Acceptance gate

New functionality, no prior behaviour to preserve — 100% pass on this
epic's own new tests, plus the full Docker suite with no new regressions
and `golden/{events,db}` regenerated + reviewed.
---
## Epic context — events-callbacks

**Contract.** `event[cached/not-cached]` implementation, detached-thread callback
dispatch with exception isolation, and an `AuditSink` hook on `OnChange` for `phi`
fields. Needs `ComplianceContext` and the `AuditSink` stub from Foundation. No
epic technically depends on this; the serialization redaction-hook design is
described as benefiting from seeing this audit-hook pattern first (precedent, not
a dependency).

**Files.** `Logger/`, new `Callback/` module.
