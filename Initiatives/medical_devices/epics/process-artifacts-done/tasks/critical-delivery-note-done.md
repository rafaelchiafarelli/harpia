> **Folded 2026-08-29** into `ComplianceReport/requirements.py` by the traceability-matrix task. This file is kept as the historical raw-material note; the live catalog entry is the source of truth.

## `ComplianceReport/` note for the critical-delivery epic (`critical` delivery)

- **Depends on:** the sbom-emission task merged (`ComplianceReport/` module exists).
- **Origin:** raised by the critical-delivery epic
  (`../../critical-delivery/`).
  `alarm_event` carries a `phi` field, so the critical-delivery epic's work is `phi`-adjacent
  per the effort's definition of done (master plan §4) and owes a
  traceability note — but `ComplianceReport/` is this epic's module, not
  the critical-delivery epic's, so the note is written here.
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering the
  `critical` message-type modifier, the delivery-guarantee runtime
  (`Compliance/runtime/harpia_delivery.h`), and the `ZmqAdapter` wiring —
  what changed, why, and which tests cover it — as raw material for the traceability-matrix task's
  traceability matrix.
- **Tests:** covered by the traceability-matrix task's matrix spot-check (one row per annotated
  construct).

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
