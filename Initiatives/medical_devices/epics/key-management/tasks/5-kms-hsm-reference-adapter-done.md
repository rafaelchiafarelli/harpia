## KMS/HSM reference adapter + extension-point docs

- **Depends on:** task 1, task 2 merged.
- **Deliverable:** documented extension point for swapping `KeyProvider`
  backends; at least one reference adapter to an external KMS/HSM-class
  system (exact vendor TBD — the point is proving the interface is real,
  not picking a vendor).
- **Guarantees:** the adapter implements task 1's interface with no extra
  required hooks — structural proof that swapping backends doesn't need
  interface changes.
- **Tests:**
  - Unit: reference adapter passes task 1's interface contract test suite.
- **Deferred, not dropped — closed for real in the db-encryption epic's cross-epic-acceptance-gates task:** two of
  this epic's original integration tests need the db-encryption epic's DAO to exist to
  be meaningful and are **not** re-attempted here with a fake DAO:
  - write → persist → rotate KEK → read pre/post-rotation, confirming no
    full-database re-encryption occurred (only DEK re-wrap).
  - swap `KeyProvider` backend (default → this reference adapter) with
    zero changes to the db-encryption epic's generated DAO code.

### Landed as

- `Crypto/runtime/harpia_key_provider_kms.h` —
  - `KmsClient` (ABC): the extension seam an integrator implements for
    their KMS/HSM. Four ops, all opaque bytes + an integer version, no
    harpia types in / no KMS types out: `active_version() const`,
    `wrap(version, dek_material)`, `unwrap(version, wrapped) →
    optional<string>`, `rotate()`.
  - `KmsKeyProvider : public KeyProvider` — routes every `KeyProvider` op
    to the seam and adds nothing (DEK minted locally, KMS wraps it; per-DEK
    shred is a local set since most KMS only delete whole versions).
    Trailing defaulted `AuditSink&` (task 4).
  - `MockKms : public KmsClient` — in-header reference impl (in-memory key
    versions, placeholder XOR) for tests / local dev, ships like
    `NoOpAuditSink`. `forget_version(v)` stands in for "the KMS deleted a
    key version".
- `Crypto/key_provider_common.py` — `KEY_PROVIDER_KMS_RUNTIME` / `_SRC` /
  `_DEPS`.
- `UnitTests/test_kms_key_provider.py` — 5 g++-gated tests: contract
  conformance via `MockKms`; per-DEK shred + KMS version retirement both →
  `nullopt`; audit wiring; the SAME `KeyProvider&` round-trip against
  `InMemoryKeyProvider` and `KmsKeyProvider` unchanged (the "no interface
  change to swap backends" proof).
- Additive — no generator code touched, no golden impact. Host 191 passed;
  full Docker suite 263 passed, 4 skipped.
- The two deferred integration tests above are the db-encryption epic's cross-epic-acceptance-gates task.
