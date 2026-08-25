# Track E — Events/callbacks

## Receives (must be done before this track starts)

- **F1, F3** from Foundation (see `../thread-3-message-behavior/README.md`)
  — `ComplianceContext`, and the `AuditSink` stub E.3 wires a call into.
- Nothing from Track F — no file overlap, no functional dependency (Track
  F sequenced after only as a mild preference, not a requirement — see
  the thread README).

## Gives (what "done" means here, consumed by whom)

- `event[cached/not-cached]` implementation, detached-thread callback
  dispatch with exception isolation, and an `AuditSink` hook on
  `OnChange`.
- **Consumed by:** no other track technically depends on this one.
  **Flag:** Track F's redaction-hook design is described as benefiting
  from seeing this track's audit-hook pattern already in place — that's
  a design precedent, not a file or interface dependency, so it isn't
  listed as a hard "receives" item on Track F's side.

## Files this track touches

- `Logger/`, new `Callback/` module (per `harpia_medical_master_plan.md`
  §2's track table). **Flag:** no more specific filenames inside
  `Callback/` are named in the plan docs — not guessing further.

---


