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
