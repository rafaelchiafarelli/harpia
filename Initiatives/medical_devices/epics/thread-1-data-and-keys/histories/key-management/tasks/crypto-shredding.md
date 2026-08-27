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

**O.1 note:** `InMemoryKeyProvider::forget_kek_version()` already exists as
a stand-in so O.1's tests could exercise the unknown-version unwrap path
(`unwrap_dek` → `nullopt`). O.3 formalizes discard semantics (per-DEK, not
per-KEK-version) and the real backends' version.
