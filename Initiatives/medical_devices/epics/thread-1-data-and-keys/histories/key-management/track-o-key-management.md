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
  decrypt-on-read of `phi` columns — see `../db-encryption/track-a-db-encryption.md`).
  Track C (Session 2, TLS stack) also consumes the F5 `CryptoBackend`
  seam this track links against, but does **not** consume Track O's
  `KeyProvider` directly — the two tracks share the seam, not each
  other's output. No other documented consumer.
- Two of this track's own integration tests (KEK-rotation round trip,
  backend-swap-with-zero-DAO-changes) can't fully close until Track A's
  DAO exists — see O.5 and `../db-encryption/track-a-db-encryption.md`'s A.4.

## Files this track touches

- New `Crypto/` module (per `harpia_medical_master_plan.md` §2's track
  table). **Flag:** the plan docs don't name specific files inside
  `Crypto/` beyond the module itself — not guessing further than that.

## Sessions

One file per session in `tasks/`. A `-done` suffix on the filename is the
done marker (no status line inside).

- `tasks/key-provider-interface-done.md` — O.1
- `tasks/default-local-provider-done.md` — O.2
- `tasks/crypto-shredding.md` — O.3
- `tasks/zeroization-and-audit.md` — O.4
- `tasks/kms-hsm-reference-adapter.md` — O.5

## Watch for

- O.5 and Track A's A.4 are a matched pair — don't merge O.5 and consider
  this track "fully tested" without coming back for A.4.
