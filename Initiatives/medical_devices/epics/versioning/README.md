# Track L — Versioning/git integration

## Decided (2026-08-23): option 2 — folded into Track M's `ComplianceReport/` output

This track's original deliverable was "version stamps feeding the
registry's 'associated version / calculated version' fields." That
registry was Track I's — Track I never got built as scoped; the problem
it targeted (crash/interrupt recovery) shipped 2026-08-19 via a different
mechanism that has no registry at all (see `../foundation.md`'s
2026-08-23 update for the full trace). No fork-tracking/versioning code
exists anywhere in the current codebase, so the underlying feature (git
fork-tracking for generated projects) is still a real, unbuilt gap — the
open question was specifically *where the version stamps live now*.

**Resolved:** fold it into Track M's `ComplianceReport/`/SBOM output
instead of building a new mechanism. Track M already has a per-project
artifact module; version lineage becomes one more field in something it
already emits, rather than a standalone registry or sidecar file. This
replaces the old "shares registry version-stamp fields with Track I"
coupling with a new one: **this track now depends on Track M, not on
Track I** (which doesn't exist as a task at all — see
`../thread-4-platform-infra/README.md`).

## Receives (must be done before this track starts)

- **F1** from Foundation (see `../thread-4-platform-infra/README.md`).
- **Track M's Session M.1** (`track-m-process-artifacts.md`) merged — the
  `ComplianceReport/` module and its SBOM emission must exist before this
  track can add fields to it. Not all of Track M — just far enough that
  the module and its base schema exist.

## Gives (what "done" means here, consumed by whom)

- Git fork-tracking metadata (version stamps, fork lineage) emitted as
  fields within Track M's existing `ComplianceReport/`/SBOM output — not
  a separate artifact.
- **Consumed by:** Track M's output is what a regulatory submission
  reads; this track's fields become part of that same evidence, not a
  separate consumer relationship. Effectively, this track extends Track M
  in place rather than standing fully independent of it.

## Files this track touches

- `ComplianceReport/` (Track M's module — see `track-m-process-artifacts.md`),
  not `Util/`/`main.py` orchestration the way the original scoping (tied
  to Track I) assumed. **Flag:** collecting the actual git state (commit
  hash, fork lineage) still needs *some* code to shell out to
  `git`/read `.git/` — plausibly a small new `Util/` helper — but neither
  the master plan nor this reconciliation commits to that shape ahead of
  L.1 actually being built. Not guessing a specific new filename.

---

## Session L.1 — Git fork-tracking metadata collection

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

## Session L.2 — Wire version stamps into Track M's `ComplianceReport/` output

- **Depends on:** L.1 merged; Track M's Session M.1 merged (the
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
  L.1, not a missing/broken artifact.

## Watch for

- Don't start L.1 or L.2 before Track M's M.1 is at least merged — L.2
  specifically has a hard dependency on the module existing.
- This track no longer touches `main.py` orchestration the way the
  original Track-I-coupled scoping assumed — don't carry that assumption
  forward into implementation without re-checking it against L.1's actual
  shape once built.
