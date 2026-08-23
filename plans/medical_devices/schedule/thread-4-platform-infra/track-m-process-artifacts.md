# Track M — Process artifacts (SBOM, traceability matrix, jurisdiction docs)

**Note:** this is the one track where `jurisdiction[]` actually drives
different output — everywhere else it's inert past F1
(`harpia_medical_master_plan.md` §0a).

## Receives (must be done before this track starts)

- **F1** from Foundation (see `../thread-4-platform-infra/README.md`).
- **Soft input, not a start-blocking precondition:** this track is "the
  consumer of every other track's `ComplianceReport/` notes" — Track A
  (Thread 1), Track C (Thread 2), Track E/F (Thread 3), Track P
  (Thread 5) all write a one-paragraph note there as part of their own
  definition of done. M.2/M.3 below need those notes to have real
  content, but the master plan doesn't gate *starting* this track on all
  of them landing first — it gates *considering M done* on checking they
  actually did.

## Gives (what "done" means here, consumed by whom)

- SBOM (CycloneDX/SPDX), a traceability matrix, and jurisdiction-selected
  doc templates (fda/eu_mdr/anvisa) stamping the same underlying evidence
  into different paperwork shells.
- **Consumed by:** the regulatory submission this whole master plan is
  building toward — a terminal artifact, not an input to another track.
  **Exception, decided 2026-08-23:** Track L (`track-l-versioning.md`)
  now extends this track's `ComplianceReport/` output with git
  fork-tracking/version-stamp fields, once Session M.1 has merged — not a
  consumer in the usual sense, more like Track L builds on top of this
  track's own module rather than reading a finished artifact from it.

## Files this track touches

- New `ComplianceReport/` module (per `harpia_medical_master_plan.md`
  §2's track table) — the same module every other track (A/C/E/F/P)
  writes its one-paragraph note into.

---

## Session M.1 — SBOM emission

- **Depends on:** F1 (Foundation).
- **Deliverable:** SBOM emission (CycloneDX/SPDX format).
- **Tests:**
  - Unit: SBOM schema validation.

## Session M.2 — Traceability matrix

- **Depends on:** M.1 merged.
- **Deliverable:** a traceability matrix — one row per
  requirement-annotated construct, drawing on other tracks'
  `ComplianceReport/` notes (see Receives above).
- **Tests:**
  - Unit: one matrix row per annotated construct.
  - Integration: full pipeline run on `HarpiaTest`, spot-check matrix
    rows against known `phi` fields and their Track A/E tests.

## Session M.3 — Jurisdiction-selected doc templates

- **Depends on:** M.1, M.2 merged.
- **Deliverable:** jurisdiction-selected doc templates (fda/eu_mdr/anvisa)
  — same underlying SBOM + traceability evidence, different paperwork
  shell per `jurisdiction[]`.
- **Tests:**
  - Integration: output format correctly follows the selected
    jurisdiction's template.
- **Acceptance gate:** doc output differs correctly across the three
  jurisdiction templates for the *same* underlying evidence (same SBOM,
  same traceability rows — only the template shell changes).

## Watch for

- Before considering this track "done": check that Track A, Track C,
  Track E/F, and Track P's `ComplianceReport/` notes actually landed —
  M.2/M.3's outputs are only as complete as those notes are.
