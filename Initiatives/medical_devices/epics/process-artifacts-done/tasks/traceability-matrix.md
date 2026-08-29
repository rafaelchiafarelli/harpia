## Traceability matrix

- **Depends on:** the sbom-emission task merged.
- **Deliverable:** a traceability matrix — one row per
  requirement-annotated construct, drawing on other tracks'
  `ComplianceReport/` notes (see Receives above).
- **Tests:**
  - Unit: one matrix row per annotated construct.
  - Integration: full pipeline run on `HarpiaTest`, spot-check matrix
    rows against known `phi` fields and their the db-encryption epic/E tests.
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
