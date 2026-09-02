## `ComplianceReport/` note for the events-callbacks epic (`phi` OnChange audit)

- **Depends on:** the sbom-emission task merged (`ComplianceReport/` module exists).
- **Origin:** raised by the events-callbacks epic
  (`../../events-callbacks-done/`), task 3 (`full-round-trip`). That task's own
  deliverable text calls for a one-paragraph `ComplianceReport/` note, but
  `ComplianceReport/` is this epic's module, not events-callbacks' — so the
  note is written here, same as `phi-db-encryption-note.md` /
  `critical-delivery-note.md`.
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering the
  events-callbacks epic's `phi` OnChange audit — what changed, why, and
  which tests cover it — as raw material for the traceability-matrix task's
  matrix:
  - `EventChannel<T>` (`Callback/runtime/harpia_event_cache.h`, tasks
    1–3): in-process pub/sub per `event` message type with cached /
    not-cached last-value semantics (task 1), detached-thread dispatch +
    per-callback exception isolation (task 2), and — task 3 — an
    `AuditSink*` (default `default_audit_sink()`, retargeted at startup via
    `set_audit_sink()`) plus baked-in `audit_subject_` (the table/name) and
    `audit_phi_fields_` (comma-joined `phi` field names) that `CallbackAdapter`
    fills from the message model.
  - **Two OnChange audit records, both value-free (Rule 5 — `record()`'s
    signature structurally cannot carry a field value):**
    - `("phi_event_dispatch", <table/name>, <phi field names>)` — recorded
      by `EventChannel::publish()` on the calling thread, once per publish
      of a `phi`-bearing event type, regardless of subscriber count; the
      cached replay on `subscribe()` does not record it. A non-`phi` event
      type never records (its `audit_phi_fields_` is empty).
    - `("phi_event_onchange", <table>, <phi cols>)` — recorded by the
      generated CRUDL DAO of a message that is *both* `event` and
      `phi`-bearing, immediately after the `<name>_channel().publish(msg)`
      call in `create()` / `update()` (never `read`/`list`/`remove`).
      "A persisted `phi` change reached the in-process event bus."
    - a swallowed callback exception also records
      `("event_callback_exception", <table/name> or "<event>", "")`.
  - `harpia_audit_sink.h` (Foundation F3) is shipped into
    `generated/cpp/events/` alongside `harpia_event_cache.h`.
  - Fixture: `alarm_event` (`critical event message` + `phi string
    patient_id` + `alarm_event_table`) in `HarpiaTest/Include/file3.harpia`.
  - Tests: `UnitTests/test_events_callbacks.py` — structural (the two audit
    call sites, the channel's baked-in phi metadata, the runtimes shipped),
    g++ runtime (one `phi_event_dispatch` per publish, non-phi records
    none, `event_callback_exception`, `set_audit_sink` retarget), and the
    protoc-gated headline round-trip (subscribe → `dao.create(phi msg)` →
    callback fires with the right payload and the sink saw `phi_create` +
    `phi_event_onchange` + `phi_event_dispatch`).
- **Tests:** covered by the traceability-matrix task's matrix spot-check (one row per annotated
  construct).

---
## Epic context — process-artifacts

**Contract.** SBOM (CycloneDX/SPDX), a traceability matrix, jurisdiction-selected
doc templates (fda/eu_mdr/anvisa), and the `ComplianceReport/` module every
`phi`-adjacent epic writes a one-paragraph note into. This is the one place
`jurisdiction[]` actually drives different output. Needs `ComplianceContext` from
Foundation. Terminal artifact — feeds the regulatory submission, not another epic
(except versioning, which extends the `ComplianceReport/` output once
sbom-emission has merged).

**Files.** New `ComplianceReport/` module.

**Watch for.** Before considering this epic done: check the `ComplianceReport/`
notes from db-encryption, transport-authn, events-callbacks / serialization, and
dds-transport actually landed — the matrix is only as complete as those notes.
