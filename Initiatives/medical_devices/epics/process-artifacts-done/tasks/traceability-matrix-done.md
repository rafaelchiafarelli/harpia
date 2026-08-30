## Traceability matrix

Scoped 2026-08-29. **Task 2** of the process-artifacts epic. Extends the
`ComplianceReport/` module (task 1) to emit a requirement→code→evidence
matrix for the generated project.

### Decisions (settled during scoping — do not re-litigate)

- **Row granularity: construct × applicable requirement.** A row is
  `(schema construct, one compliance requirement that applies to it, the
  mechanism that enforces it, test evidence)`. A `phi` field on a
  table-bearing message yields ~3 rows (Rule 1 encryption, Rule 1
  redaction, Rule 5 audit-on-access); a `phi` field on a table-less
  message yields the redaction row only; a `critical` message yields ~2
  (Rule 4a ordered delivery, Rule 3 integrity). Plus a fixed set of
  project-level rows (Rule 0, Rule 6a, the audited redaction opt-out, the
  SBOM itself).
- **Artifacts:** `generated/ComplianceReport/traceability.json` is the
  source of truth (the jurisdiction-template-selection task renders it);
  `generated/ComplianceReport/traceability.md` ships alongside for direct
  human review. No timestamp field — fully deterministic, golden-snapshotted.
- **Requirements catalog is checked-in:** `ComplianceReport/requirements.py`
  — `[{id, rule_ref, text, applies_to: phi_field | critical_message |
  project, mechanism, test_refs}]`. **This task folds the three existing
  `*-note.md` files** (`serialization-redaction-note`,
  `phi-db-encryption-note`, `critical-delivery-note`) into that catalog and
  marks those three note task-files `-done`. Future note-producing tasks
  add a catalog entry, not a prose file.

### Contract

- **Depends on:** the sbom-emission task merged (`ComplianceReport/`
  module exists).
- **Delivered:**
  - `ComplianceReport/requirements.py` — the catalog, seeded from the
    design rules (`harpia_sensitive_data_design_rules.md` Rules 0/1/3/4a/5/6a)
    and the three folded notes. Each entry carries explicit `test_refs`
    (`module.py::test_prefix*` form).
  - `ComplianceReport.py` grows a `_traceability()` builder: walk
    `self.messages`; for each `critical` message emit its
    `critical_message` requirement rows; for each `phi` variable emit its
    `phi_field` rows (the DB-encryption / audit rows only when the message
    is table-bearing); emit the fixed `project` rows once. Rows sorted by
    `(construct, requirement_id)`.
  - `Process()` also writes `traceability.json`
    (`{"rows": [{construct, requirement_id, rule_ref, mechanism,
    evidence: [...]}, ...]}`) and `traceability.md` (a rendered table).
  - `run_pipeline.py` `_collect_compliancereport` picks both up (already
    globs the dir — confirm it copies `*.json` + `*.md`, not just
    `bom.json`); `test_golden.py::test_compliancereport` snapshots them.
- **Fold-in:** move the substance of the three `*-note.md` files into
  `requirements.py` entries, then `git mv` each to `*-done.md`. Update the
  epic `README.md` "Watch for" line (the outstanding notes list) and the
  `epics/README.md` process-artifacts row.

### Tests

- Unit (`UnitTests/test_traceability.py`, pure Python): every row has a
  non-empty `construct`, a `requirement_id` present in `requirements.py`,
  a non-empty `mechanism`, and ≥1 `evidence` ref; the row count equals the
  catalog-derived expectation computed in-test from the `HarpiaTest`
  fixture's `phi` fields / `critical` messages (not hardcoded);
  `traceability.md` has one table row per `traceability.json` row.
- Integration: full `run_pipeline.py` on `HarpiaTest` — spot-check that the
  `patient_vitals.patient_id` × Rule-1-encryption row references a
  `test_stage8_db.py` test, and the `alarm_event` × Rule-4a row references
  `test_critical_delivery_roundtrip.py`.
- Golden: `traceability.json` + `traceability.md` snapshotted under
  `UnitTests/golden/compliancereport/`.

### Out of scope

- Jurisdiction rendering (task 3 — `jurisdiction-template-selection`).
- Rows for epics that produced no `ComplianceReport/` note
  (key-management, db-segregation, schema-evolution): if they want matrix
  coverage, that is a note-fold entry added to `requirements.py` by a
  later task, not invented here. Their machinery is still *referenced*
  where it underpins a listed requirement (e.g. `KeyProvider` inside the
  Rule 1 encryption mechanism text).
- Version / git lineage rows (versioning epic).

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
