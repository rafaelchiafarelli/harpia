> **Folded 2026-08-29** into `ComplianceReport/requirements.py` by the traceability-matrix task. This file is kept as the historical raw-material note; the live catalog entry is the source of truth.

## `ComplianceReport/` note for the db-encryption epic (`phi` DB field-level encryption)

- **Depends on:** the sbom-emission task merged (`ComplianceReport/` module exists).
- **Origin:** raised by the db-encryption epic
  (`../../db-encryption/`
). the compliancereport task's own deliverable text calls for a one-paragraph
  `ComplianceReport/` note, but `ComplianceReport/` is this epic's module
  not the db-encryption epic's — so the note is written here, same as the critical-delivery epic's
  `critical-delivery-note.md`.
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering Track
  A's `phi` DB field-level encryption — what changed, why, and which tests
  cover it — as raw material for the traceability-matrix task's traceability matrix:
  - `EncryptedColumn` runtime (`Crypto/runtime/harpia_encrypted_column.h`):
    envelope encryption of a `phi` column's value on the DAO write path
    (`encrypt_field` = generate DEK → seal → wrap DEK with the active KEK →
    frame + `enc:v1:` hex) and open on the read path (`decrypt_field*`)
    built on the key-management epic's `KeyProvider`; an unrecoverable value → 0/"" (Rule
    5), never a throw.
  - `CrudlAdapter` wiring: a `phi`-bearing message's DAO holds a
    `KeyProvider&` + an `AuditSink&` (both defaulted ctor params, so a
    non-`phi` DAO is byte-unchanged); create/update encrypt, read/list
    decrypt; the Local / KMS backend headers ship into `generated/cpp/
    crypto/` so a deployment can pass a persistent provider.
  - Audit: exactly one `AuditSink.record()` per `phi`-touching CRUDL op
    (`phi_create` / `phi_read` / `phi_update` / `phi_delete` / `phi_list`)
    subject = table, detail = the `phi` column names — never a value.
  - `project.harpia.yaml` landed at the repo root (roadmap Phase 0).
  - Tests: `UnitTests/test_stage8_db.py::test_a1_*` / `test_a2_*` /
    `test_a3_*` (encrypt/decrypt round trip per type, raw-SQL ciphertext
    check, persist/restart across separate processes, wrong-key cannot
    recover, one-audit-record-per-op with value-free detail).
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
