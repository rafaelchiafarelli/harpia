# Session 3 — Message Behavior

Covers Track E (events/callbacks) then Track F (serialization
unification). One session, sequential.

---

## Preconditions

Foundation (F1–F5) merged to `main`. Confirm before starting:
- `ComplianceContext` is threaded through `main.py` and every stage.
- `field.is_phi` exists on parsed fields (Track F needs this for
  redaction).
- `AuditSink` (no-op stub) exists and is injectable (Track E needs this
  for OnChange hooks).
- A tagged F4 regression baseline exists.

---

## Execution order

**Track E first, then Track F, same session.** Not a hard dependency —
Track F's redaction hook design benefits from seeing Track E's audit-hook
pattern already in place, but Track F could technically start
independently if you need to reorder for scheduling reasons.

---

## Contracts

### Track E — Events/callbacks
- **Depends on:** F1, F3.
- **Deliverables:** `event[cached/not-cached]` implementation; detached-
  thread callback dispatch with try-catch isolation; `AuditSink` hook on
  OnChange.
- **Guarantees:** create/change/update fire events, read never does;
  callback exceptions never propagate to the caller thread; cached
  subscriptions receive the last value immediately on subscribe.
- **Out of scope:** the serialization work (Track F).
- **Tests:**
  - Unit: cached vs. not-cached delivery semantics; callback exception
    isolation.
  - Integration: subscribe → mutate → assert callback fires with correct
    payload and, for `phi` fields, an audit record is emitted.
  - Acceptance gate: new functionality, no prior behavior to preserve —
    gate is 100% pass on its own new tests.

### Track F — Serialization unification (YAML + redaction)
- **Depends on:** F2.
- **Deliverables:** `YamlAdapter/`; unified `toString` path across
  JSON/XML/YAML; `phi` redaction applied uniformly per the
  architecture-doc safety-valve language:
  - fields marked `phi` are represented in `toString` output as a fixed
    redacted placeholder by default — never omitted from the output
    structure, never causing an error or crash.
  - unredacted output only emitted when an explicit, non-default flag is
    set at build or call time (e.g. `--allow-phi-print`); any use of that
    flag is itself an audited event, not a silent one.
- **Guarantees:** `toString` never crashes, never omits structure; `phi`
  values redacted by default in all three formats; the unredacted-output
  flag, when used, triggers an audit record.
- **Tests:**
  - Unit: redaction present in all three formats for `phi` fields.
  - Unit: unredacted flag reveals the real value AND emits an audit
    record.
  - Integration: round-trip a message with `phi` fields through all
    three formats; structure/keys always present, values redacted by
    default.
  - Acceptance gate: existing JSON/XML golden snapshots (14.5/14.6)
    unchanged for non-`phi` messages.

---

## Definition of done (applies to every track above)

- Unit tests for every new construct/behavior introduced.
- Integration test covering end-to-end behavior in a realistic path.
- Full F4 regression baseline still passes.
- Both tracks touch `phi`-adjacent code: one-paragraph note added to
  `ComplianceReport/` per track describing what changed and why (feeds
  Track M later).

## Watch for

- Test fixture reference: use `HarpiaTest/test_medical.harpia` (has a
  zero-`phi`, a mixed, and a fully-`phi` message) to exercise Track F's
  redaction across the full spectrum, not just a single hand-picked field.
