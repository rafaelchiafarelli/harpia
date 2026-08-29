## Jurisdiction-selected doc templates

- **Depends on:** the sbom-emission task, the traceability-matrix task merged.
- **Deliverable:** jurisdiction-selected doc templates (fda/eu_mdr/anvisa)
  — same underlying SBOM + traceability evidence, different paperwork
  shell per `jurisdiction[]`.
- **Tests:**
  - Integration: output format correctly follows the selected
    jurisdiction's template.
- **Acceptance gate:** doc output differs correctly across the three
  jurisdiction templates for the *same* underlying evidence (same SBOM,
  same traceability rows — only the template shell changes).
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
