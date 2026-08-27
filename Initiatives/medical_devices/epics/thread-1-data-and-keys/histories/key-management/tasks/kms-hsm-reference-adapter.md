## Session O.5 — KMS/HSM reference adapter + extension-point docs

- **Depends on:** O.1, O.2 merged.
- **Deliverable:** documented extension point for swapping `KeyProvider`
  backends; at least one reference adapter to an external KMS/HSM-class
  system (exact vendor TBD — the point is proving the interface is real,
  not picking a vendor).
- **Guarantees:** the adapter implements O.1's interface with no extra
  required hooks — structural proof that swapping backends doesn't need
  interface changes.
- **Tests:**
  - Unit: reference adapter passes O.1's interface contract test suite.
- **Deferred, not dropped — closed for real in Track A's A.4:** two of
  this track's original integration tests need Track A's DAO to exist to
  be meaningful and are **not** re-attempted here with a fake DAO:
  - write → persist → rotate KEK → read pre/post-rotation, confirming no
    full-database re-encryption occurred (only DEK re-wrap).
  - swap `KeyProvider` backend (default → this reference adapter) with
    zero changes to Track A's generated DAO code.
