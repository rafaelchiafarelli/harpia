## `EncryptedColumn<T>` wrapper + encrypt-on-write

- **Deliverable:** `EncryptedColumn<T>`-style wrapper used when
  `field.is_phi`, built on the key-management epic's envelope-encryption scheme; DAO
  create/update paths encrypt-on-write via `KeyProvider`.
- **Guarantees:** `phi` values are never persisted in plaintext on the
  write path; non-`phi` fields see no behavior/perf change.
- **Out of scope:** decrypt-on-read (task 2), `AuditSink` wiring (task 3).
- **Tests:**
  - Unit: encrypt round trip per supported type.
  - Integration: write → persist → raw SQL query (bypassing the DAO)
    shows ciphertext, not plaintext.