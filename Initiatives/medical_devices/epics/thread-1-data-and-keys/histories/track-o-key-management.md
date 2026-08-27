# Track O — Key management

Pluggable `KeyProvider`: envelope encryption, rotation, crypto-shredding,
key-access auditing. **Why this needs to be a library-level interface,
not a fixed implementation:** Harpia is consumed by different
manufacturers with different infrastructure — a hospital-integrated
deployment may have its own KMS/HSM already; an embedded device may have
none. The library defines the contract; the integrator supplies (or
accepts a safe default for) the backend. **Decision closed: one
implementation per project, not one per jurisdiction**
(`harpia_medical_master_plan.md` §0a) — gated by `risk_class`, not forked
per jurisdiction.

## Receives (must be done before this track starts)

- **F1, F3, F5** from Foundation (see `../thread-1-data-and-keys/README.md`)
  — `ComplianceContext`, `AuditSink` stub, and the `CryptoBackend`
  selection seam this track's crypto operations link against.
- Nothing from Track H, A, or K — Track O has no dependency on any
  sibling track in this thread.

## Gives (what "done" means here, consumed by whom)

- A `Crypto/KeyProvider` interface, a default local implementation, and a
  KMS/HSM reference adapter — all shaped around envelope encryption
  (KEK-wraps-DEK), with rotation, crypto-shredding, zeroization, and full
  `AuditSink` wiring on every key operation.
- **Consumed by:** Track A (uses `KeyProvider` for encrypt-on-write/
  decrypt-on-read of `phi` columns — see `track-a-db-encryption.md`).
  Track C (Session 2, TLS stack) also consumes the F5 `CryptoBackend`
  seam this track links against, but does **not** consume Track O's
  `KeyProvider` directly — the two tracks share the seam, not each
  other's output. No other documented consumer.
- Two of this track's own integration tests (KEK-rotation round trip,
  backend-swap-with-zero-DAO-changes) can't fully close until Track A's
  DAO exists — see O.5 below and `track-a-db-encryption.md`'s A.4.

## Files this track touches

- New `Crypto/` module (per `harpia_medical_master_plan.md` §2's track
  table). **Flag:** the plan docs don't name specific files inside
  `Crypto/` beyond the module itself — not guessing further than that.

---

## Session O.1 — `KeyProvider` interface + envelope-encryption shape

- **Depends on:** F1, F3, F5 (Foundation).
- **Deliverable:** abstract `Crypto/KeyProvider` interface — generate/
  retrieve the active key-encryption-key (KEK), fetch a KEK by version,
  wrap/unwrap a data-encryption-key (DEK), rotate (produces a new KEK
  version without touching existing data). Shape the interface around
  **envelope encryption** from the start: each `phi` column/record gets
  its own DEK; the DEK encrypts the value; the KEK only wraps DEKs. This
  is what makes rotation cheap (re-wrap DEKs, O(number of keys)) instead
  of a full re-encryption pass (O(data size)) — bake the shape in now,
  don't retrofit it after O.2.
  Also build a minimal in-memory/dummy `KeyProvider` implementation, used
  only to exercise this session's own tests — not the real default
  backend (that's O.2).
- **Guarantees:** interface compiles and instantiates standalone against
  the dummy impl; `rotate()` never requires touching existing ciphertext.
- **Out of scope:** no real backend, no KMS, no crypto-shredding, no
  `AuditSink` wiring, no zeroization — interface + envelope shape only.
- **Tests:**
  - Unit: envelope wrap/unwrap round trip against the dummy impl.
  - Unit: rotation produces a new KEK version while existing DEKs remain
    unwrappable via their recorded version reference.

## Session O.2 — Default local `KeyProvider` + fail-safe acknowledgment gate

- **Depends on:** O.1 merged.
- **Deliverable:** a concrete default `KeyProvider` (e.g. platform-
  keystore/TPM-sealed local storage) implementing O.1's interface, for
  integrators with no external KMS. Per the fail-safe-default rule: when
  the active compliance profile implies PHI at scale, using this default
  backend requires an explicit acknowledgment — not silent use — prompting
  a real KMS-integration decision instead of quietly shipping the
  fallback into production.
- **Guarantees:** the default impl passes O.1's own wrap/unwrap/rotate
  test suite unmodified (interface conformance); the acknowledgment gate
  blocks silent use under a PHI-at-scale profile.
- **Out of scope:** KMS/HSM reference adapter (O.5), crypto-shredding
  (O.3), zeroization/audit wiring (O.4).
- **Tests:**
  - Unit: default impl satisfies O.1's interface contract tests.
  - Unit: PHI-at-scale profile without acknowledgment refuses to proceed;
    with acknowledgment, proceeds.

## Session O.3 — Crypto-shredding

- **Depends on:** O.1 merged (works against either O.1's dummy or O.2's
  default impl — doesn't need O.2 specifically).
- **Deliverable:** the ability to permanently discard a specific DEK,
  rendering only that record's data unrecoverable without touching or
  rewriting the ciphertext itself — the practical mechanism for
  GDPR/LGPD-style right-to-erasure requests without a destructive
  database rewrite.
- **Guarantees:** discarding a DEK is sufficient and necessary to make
  that DEK's data permanently unrecoverable.
- **Tests:**
  - Unit: crypto-shred — discard a DEK, confirm its ciphertext is
    permanently unrecoverable even with the KEK still available.

## Session O.4 — Zeroization + `AuditSink` wiring

- **Depends on:** O.1 merged; F3's `AuditSink` stub (Foundation).
- **Deliverable:** key material cleared from memory after use, not left
  to garbage collection/deallocation timing; every key operation
  (generate, wrap, unwrap, rotate, shred) routed through `AuditSink` — key
  management is itself a security-relevant, auditable activity.
- **Guarantees:** no raw key material ever appears in source code,
  generated config, or logs in plaintext (mechanically checkable).
- **Tests:**
  - Unit: mock `AuditSink`, assert exactly one call per key-operation
    type (generate/wrap/unwrap/rotate/shred).
  - Unit/CI: grep-style scan across generated output and logs asserting
    no raw key material ever appears in plaintext.

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

## Watch for

- O.5 and Track A's A.4 are a matched pair — don't merge O.5 and consider
  this track "fully tested" without coming back for A.4.
