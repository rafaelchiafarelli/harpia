## Session M.x — `ComplianceReport/` note for Track A (`phi` DB field-level encryption)

- **Depends on:** M.1 merged (`ComplianceReport/` module exists).
- **Origin:** raised by Track A
  (`../../../thread-1-data-and-keys/histories/db-encryption/track-a-db-encryption.md`,
  Session A.3). A.3's own deliverable text calls for a one-paragraph
  `ComplianceReport/` note, but `ComplianceReport/` is this track's module,
  not Track A's — so the note is written here, same as Track D's
  `critical-delivery-note.md`.
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering Track
  A's `phi` DB field-level encryption — what changed, why, and which tests
  cover it — as raw material for M.2's traceability matrix:
  - `EncryptedColumn` runtime (`Crypto/runtime/harpia_encrypted_column.h`):
    envelope encryption of a `phi` column's value on the DAO write path
    (`encrypt_field` = generate DEK → seal → wrap DEK with the active KEK →
    frame + `enc:v1:` hex) and open on the read path (`decrypt_field*`),
    built on Track O's `KeyProvider`; an unrecoverable value → 0/"" (Rule
    5), never a throw.
  - `CrudlAdapter` wiring: a `phi`-bearing message's DAO holds a
    `KeyProvider&` + an `AuditSink&` (both defaulted ctor params, so a
    non-`phi` DAO is byte-unchanged); create/update encrypt, read/list
    decrypt; the Local / KMS backend headers ship into `generated/cpp/
    crypto/` so a deployment can pass a persistent provider.
  - Audit: exactly one `AuditSink.record()` per `phi`-touching CRUDL op
    (`phi_create` / `phi_read` / `phi_update` / `phi_delete` / `phi_list`),
    subject = table, detail = the `phi` column names — never a value.
  - `project.harpia.yaml` landed at the repo root (roadmap Phase 0).
  - Tests: `UnitTests/test_stage8_db.py::test_a1_*` / `test_a2_*` /
    `test_a3_*` (encrypt/decrypt round trip per type, raw-SQL ciphertext
    check, persist/restart across separate processes, wrong-key cannot
    recover, one-audit-record-per-op with value-free detail).
- **Tests:** covered by M.2's matrix spot-check (one row per annotated
  construct).
