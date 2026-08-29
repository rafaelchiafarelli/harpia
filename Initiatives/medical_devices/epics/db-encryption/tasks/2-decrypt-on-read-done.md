## Decrypt-on-read

- **Depends on:** task 1 merged.
- **Deliverable:** DAO read path decrypt-on-read via `KeyProvider`.
- **Tests:**
  - Unit: decrypt round trip per supported type.
  - Integration: write → persist → restart process → read; confirm
    decrypted value matches the original.