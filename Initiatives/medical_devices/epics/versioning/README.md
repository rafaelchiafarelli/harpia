# Versioning/git integration

## Decided (2026-08-23): option 2 — folded into the process-artifacts epic's `ComplianceReport/` output

This epic's original deliverable was "version stamps feeding the
registry's 'associated version / calculated version' fields." That
registry was the continuable-process work's — the continuable-process work never got built as scoped; the problem
it targeted (crash/interrupt recovery) shipped 2026-08-19 via a different
mechanism that has no registry at all (see `../foundation-handoff.md`'s
2026-08-23 update for the full trace). No fork-tracking/versioning code
exists anywhere in the current codebase, so the underlying feature (git
fork-tracking for generated projects) is still a real, unbuilt gap — the
open question was specifically *where the version stamps live now*.

**Resolved:** fold it into the process-artifacts epic's `ComplianceReport/`/SBOM output
instead of building a new mechanism. the process-artifacts epic already has a per-project
artifact module; version lineage becomes one more field in something it
already emits, rather than a standalone registry or sidecar file. This
replaces the old "shares registry version-stamp fields with the continuable-process work"
coupling with a new one: **this epic now depends on the process-artifacts epic, not on
the continuable-process work** (which doesn't exist as a task at all — see
`../README.md`).

## Receives (must be done before this epic starts)

- **F1** from Foundation (see `../README.md`).
- **the process-artifacts epic's sbom-emission task** (the process-artifacts epic) merged — the
  `ComplianceReport/` module and its SBOM emission must exist before this epic can add fields to it. Not all of the process-artifacts epic — just far enough that
  the module and its base schema exist.

## Gives (what "done" means here, consumed by whom)

- Git fork-tracking metadata (version stamps, fork lineage) emitted as
  fields within the process-artifacts epic's existing `ComplianceReport/`/SBOM output — not
  a separate artifact.
- **Consumed by:** the process-artifacts epic's output is what a regulatory submission
  reads; this epic's fields become part of that same evidence, not a
  separate consumer relationship. Effectively, this epic extends the process-artifacts epic
  in place rather than standing fully independent of it.

## Files this epic touches

- `ComplianceReport/` (the process-artifacts epic's module — see the process-artifacts epic),
  not `Util/`/`main.py` orchestration the way the original scoping (tied
  to the continuable-process work) assumed. **Flag:** collecting the actual git state (commit
  hash, fork lineage) still needs *some* code to shell out to
  `git`/read `.git/` — plausibly a small new `Util/` helper — but neither
  the master plan nor this reconciliation commits to that shape ahead of
  task 1 actually being built. Not guessing a specific new filename.

---

## Git fork-tracking metadata collection

- **Depends on:** F1 (Foundation).
- **Deliverable:** compute a version stamp / fork-lineage record from the
  active git state at generation time.
- **Guarantees:** projects without git present degrade gracefully — no
  crash, no forced requirement, a clearly-absent lineage record rather
  than a fabricated one.
- **Tests:**
  - Unit: version stamp matches actual git state.
  - Unit: no-git environment produces the graceful-absence case, not a
    crash.

## Wire version stamps into the process-artifacts epic's `ComplianceReport/` output

- **Depends on:** task 1 merged; the process-artifacts epic's sbom-emission task merged (the
  `ComplianceReport/` module must exist to extend).
- **Deliverable:** version stamp / fork-lineage fields added to the
  SBOM/`ComplianceReport/` output — "one more field in something it
  already emits," not a new artifact.
- **Guarantees:** version lineage is recoverable for any generated
  project by reading its `ComplianceReport/` output.
- **Tests:**
  - Integration: fork a harpia project, regenerate, confirm lineage
    recorded in the `ComplianceReport/` output and traceable back to the
    parent.
- **Acceptance gate:** no-git environments still generate successfully,
  `ComplianceReport/` output present with the graceful-absence case from
  task 1, not a missing/broken artifact.

## Watch for

- Don't start task 1 or task 2 before the process-artifacts epic's the sbom-emission task is at least merged — task 2
  specifically has a hard dependency on the module existing.
- This epic no longer touches `main.py` orchestration the way the
  original Track-I-coupled scoping assumed — don't carry that assumption
  forward into implementation without re-checking it against task 1's actual
  shape once built.
