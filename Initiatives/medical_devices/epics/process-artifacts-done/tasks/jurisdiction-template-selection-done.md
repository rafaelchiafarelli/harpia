## Jurisdiction-selected doc templates

Scoped 2026-08-29. **Task 3** (final) of the process-artifacts epic.

### Decisions (settled during scoping — do not re-litigate)

- **Same evidence, different shell only** (master plan §0a, design-rules §6):
  the SBOM section and the traceability section are rendered **byte-identical**
  across jurisdictions; only the document's header block (target regime,
  document package, regulatory framework, standards cited, review body,
  post-market obligations, and EU MDR's tamper-evidence note) changes.
- **One shared template file** `ComplianceReport/templates/compliance_report.md.tmpl`
  with `{{placeholder}}` markers filled by `str.replace` (not `.format` —
  the evidence tables contain braces). A `ComplianceReport/jurisdictions.py`
  registry maps a jurisdiction token → the header-block values.
- **Always emit a generic, jurisdiction-neutral `compliance_report.md`**
  (cites only the harmonized baseline IEC 62304 / ISO 14971). Plus one
  `compliance_report.<token>.md` for each entry in `compliance.jurisdiction`.
  An **unknown** token → the generic shell + a `> no jurisdiction-specific
  template for '<token>'` note; never an error (`jurisdiction[]` is inert
  metadata — `ComplianceContext` already accepts arbitrary strings).
- Token match is case-insensitive: `upper()`, spaces/hyphens → `_`
  (`FDA`, `EU_MDR`, `ANVISA`).
- Markdown output. **Not legal advice** — every report carries the
  design-rules §6/§9 disclaimer.

### Contract

- **Depends on:** the sbom-emission task + the traceability-matrix task
  merged (this task renders `bom.json` + `traceability.json` into shells).
- **Delivered:**
  - `ComplianceReport/jurisdictions.py` — `JURISDICTIONS` (FDA / EU_MDR /
    ANVISA) + `GENERIC`; `resolve(token) -> (key, entry_or_None)`.
  - `ComplianceReport/templates/compliance_report.md.tmpl`.
  - `ComplianceReport.py`: after the SBOM + matrix, emit the report(s) —
    `_render_report(shell, bom, rows)` fills the template (`{{sbom_table}}`
    = component table, `{{traceability_table}}` = the matrix table body,
    `{{project}}` / `{{risk_class}}` / `{{topology}}` / `{{phi_handling}}`
    from the context). write-if-different.
  - `run_pipeline.py` `_collect_compliancereport` copies `compliance_report*.md`
    verbatim (no timestamp). `test_golden.py::test_compliancereport` picks
    them up (the pipeline runs `jurisdiction: []` → snapshots the generic
    `compliance_report.md` only).
  - `ComplianceReport/CLAUDE.md` updated; `epics/README.md` process-artifacts
    row → **done**.

### Tests

`UnitTests/test_jurisdiction_templates.py` (pure Python, direct `Process()`):
- `jurisdiction=["FDA","EU_MDR","ANVISA"]` → 4 report files (generic + 3).
- **Acceptance gate:** everything from the `## 1. Software Bill of Materials`
  heading onward is byte-identical across the FDA / EU_MDR / ANVISA reports;
  the header blocks differ (distinct `framework` / `doc_package` strings).
- `jurisdiction=[]` → only `compliance_report.md`.
- Unknown token (`["XX"]`) → `compliance_report.xx.md` with the
  "no jurisdiction-specific template" note, no crash.
- The EU_MDR report carries the IEC 81001-5-1 tamper-evidence note; FDA and
  ANVISA do not.
- Deterministic / write-if-different; no timestamp in any report.

### Out of scope

- PDF / DOCX rendering (Markdown only).
- Authoritative regulatory content — the header blocks are credible
  scaffolds with the standing "not legal advice" disclaimer, not a
  substitute for regulatory-affairs review.
- Version / git lineage in the report (versioning epic extends this later).

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
