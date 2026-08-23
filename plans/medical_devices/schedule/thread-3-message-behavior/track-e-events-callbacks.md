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

## Session E.1 — `event[cached/not-cached]` implementation

- **Depends on:** F1 (Foundation).
- **Deliverable:** `event[cached/not-cached]` firing on create/change/
  update; cached subscriptions receive the last value immediately on
  subscribe; `read` never fires an event.
- **Tests:**
  - Unit: cached vs. not-cached delivery semantics.

## Session E.2 — Detached-thread callback dispatch + exception isolation

- **Depends on:** E.1 merged.
- **Deliverable:** callback dispatch runs on a detached thread; a
  try-catch boundary ensures a callback's own exception never propagates
  to the caller thread.
- **Tests:**
  - Unit: callback exception isolation — an exception thrown inside a
    callback doesn't crash or propagate to the caller.

## Session E.3 — `AuditSink` hook on `OnChange` + full round-trip

- **Depends on:** E.1, E.2 merged; F3's `AuditSink`.
- **Deliverable:** `AuditSink` hook fires on `OnChange`, specifically for
  `phi` fields; one-paragraph `ComplianceReport/` note (feeds Track M
  later).
- **Tests:**
  - Integration: subscribe → mutate → assert the callback fires with the
    correct payload, and for `phi` fields an audit record is emitted.
- **Acceptance gate:** new functionality, no prior behavior to preserve —
  100% pass on this track's own new tests.
