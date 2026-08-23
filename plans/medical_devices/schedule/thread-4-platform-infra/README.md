# Thread 4 — Platform Infra & Expansion

Same restructuring as `thread-1-data-and-keys/` (see that folder's
README for the full rationale): one file per track, each broken into
small `Session <Track>.<n>` units (one deliverable + its own tests,
sized to fit a single sitting), each with an explicit Receives/Gives/
Files-touched contract.

**Track I is not represented here at all.** It was scoped to build a
sha256 registry for crash/interrupt recovery; that already shipped
2026-08-19 via a different mechanism (see `../foundation.md`'s
2026-08-23 update note for the full trace). Dropping it from this
restructuring isn't an oversight — see the note on Track L below for its
real fallout.

- [track-j-java-target.md](track-j-java-target.md) — **pointer only,
  2026-08-23**: multi-language codegen (Java) moved to its own standalone
  plan, `plans/multi-language-targets/` — not medical-devices-specific
  work. This file now covers only the one compliance-aware layer that
  might get added on top, once it's ready to scope.
- [track-m-process-artifacts.md](track-m-process-artifacts.md) — SBOM,
  traceability matrix, jurisdiction-selected doc templates.
- [track-n-static-fuzz-ci.md](track-n-static-fuzz-ci.md) — static/fuzz
  analysis CI.
- [track-l-versioning.md](track-l-versioning.md) — versioning/git
  integration. **Decided 2026-08-23** (option 2: folded into Track M's
  `ComplianceReport/` output) — now depends on Track M, see that file.

---

## What this whole thread receives from Foundation

- **F1** — `ComplianceContext` threaded through `main.py` and every
  stage. Track N needs nothing at all, not even this.
- **F4** — a tagged regression baseline exists.

(F1–F5 defined in `../foundation.md`. This thread doesn't need F2/F3/F5 —
none of J/M/N/L touch `phi`, `AuditSink`, or crypto-backend selection
directly.)

---

## Execution order across tracks

- **Track M's Session M.1 before Track L.** Track L now depends on
  Track M's `ComplianceReport/` module existing (see
  `track-l-versioning.md`'s 2026-08-23 decision) — start Track M first,
  or at least far enough to merge M.1, before picking up Track L.
- **Track M and Track N** — no dependencies on each other, on Track L, or
  on any other thread (§0a dropped Track N's old cross-thread parity-diff
  dependency) — run in whatever order suits. Track L is the one
  exception: it waits on Track M specifically. (Track J's own session
  breakdown moved to `plans/multi-language-targets/` — it isn't one of
  this thread's own no-dependency tracks anymore, see
  `track-j-java-target.md`'s pointer.)

### Squaring the numbers (from the original four-session plan)

At kickoff, Thread 1 (needs two concurrent session-lines for Track O and
Track H), Thread 2, and Thread 3 already account for all four
originally-available session-lines — this thread doesn't get a dedicated
one immediately. Whichever of Track O or Track H (Thread 1) finishes
first should pick up a no-dependency task as filler rather than idling
while it waits on the other — Track M or Track N from here, or Track J
from `plans/multi-language-targets/` (a different plan folder now, but
just as valid a filler pick, and just as free of a dependency on
anything else in this thread).

---

## Definition of done (every session, every track in this thread)

- Unit tests for the construct/behavior that specific session introduces.
- Integration test covering end-to-end behavior in a realistic path.
- Full F4 regression baseline still passes.
- Track M is the consumer of every other track's `ComplianceReport/`
  notes — check those notes actually landed before considering Track M
  "done" (see `track-m-process-artifacts.md`'s own "Watch for").
- **Ground Rule 6 (`../foundation.md`, added 2026-08-23):** any session
  that touches a consumer-facing template/adapter emits/updates accurate
  Doxygen doc-comments for what it touched, in the same session — not
  deferred. Applies here to M/N/L's work directly; Track J's own 10
  sessions live in `plans/multi-language-targets/` now (see that plan's
  own Ground-Rule-6-equivalent discipline, not repeated here).

## Watch for

- Track L is no longer a genuinely independent, no-dependency track like
  J/M/N — its 2026-08-23 resolution ties it to Track M's M.1. Don't pick
  it up as filler the way J/M/N can be.
- Track J's session breakdown (27 sessions, re-graded 2026-08-23 to
  match this thread's own one-deliverable-per-session grain) moved out
  of this thread entirely
  (2026-08-23) — see `track-j-java-target.md`'s pointer. Don't expect to
  find it here.
