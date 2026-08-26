# Thread 3 — Message Behavior

Same restructuring as `thread-1-data-and-keys/` (see that folder's
README for the full rationale): one file per track, each broken into
small `Session <Track>.<n>` units (one deliverable + its own tests,
sized to fit a single sitting), each with an explicit Receives/Gives/
Files-touched contract.

The smallest of the five threads — two tracks, neither internally as
large as Track O or Track C were.

- [track-e-events-callbacks.md](histories/events-callbacks/track-e-events-callbacks.md) —
  `event[cached/not-cached]`, detached-thread callback dispatch.
- [track-f-serialization.md](histories/serialization/track-f-serialization.md) — YAML adapter,
  unified `toString` path, `phi` redaction.

---

## What this whole thread receives from Foundation

- **F2** — `field.is_phi` flag available on every parsed field (Track F
  needs this for redaction).
- **F3** — `AuditSink` (no-op stub) exists and is injectable (Track E
  needs this for its `OnChange` hook).
- **F1, F4** — `ComplianceContext` threaded through; a tagged regression
  baseline exists as the diff target for acceptance gates.

(F1–F5 defined in `../foundation.md`.)

---

## Execution order across tracks

**Track E before Track F, same session-line — not a hard dependency.**
Track F's redaction-hook design benefits from seeing Track E's
`AuditSink`-on-`OnChange` pattern already built and working, but Track F
could start independently if there's a scheduling reason to reorder.
Unlike Track C/Track B in Thread 2, this ordering isn't defended as
necessary anywhere in the source docs — treat it as a mild preference,
not a rule.

---

## Definition of done (every session, every track in this thread)

- Unit tests for the construct/behavior that specific session introduces.
- Integration test covering end-to-end behavior in a realistic path.
- Full F4 regression baseline still passes.
- Both tracks touch `phi`-adjacent code: a one-paragraph
  `ComplianceReport/` note per track (feeds Track M later).
- **Ground Rule 6 (`../foundation.md`, added 2026-08-23):** any session
  that touches a consumer-facing template/adapter emits/updates accurate
  Doxygen doc-comments for what it touched, in the same session — not
  deferred. Add a row to `Initiatives/doxygen-generation/doxygen-generation.md` §4 if the work
  surfaces a pitfall not already listed there.

## Watch for

- Test fixture reference for Track F: use
  `HarpiaTest/test_medical.harpia` (has a zero-`phi`, a mixed, and a
  fully-`phi` message) to exercise redaction across the full spectrum,
  not just a single hand-picked field.
