## Crypto-shredding

- **Depends on:** task 1 merged (works against either task 1's dummy or task 2's
  default impl — doesn't need task 2 specifically).
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

**task 1 note:** `InMemoryKeyProvider::forget_kek_version()` already exists as
a stand-in so task 1's tests could exercise the unknown-version unwrap path
(`unwrap_dek` → `nullopt`). task 3 formalizes discard semantics (per-DEK, not
per-KEK-version) and the real backends' version.

### Landed as

- `Crypto/runtime/harpia_key_provider.h` — `KeyProvider` gains a pure
  virtual `shred_dek(const WrappedDek& w)`; a shared free function
  `shred_key(w)` = `"<kek_version>:<bytes>"` is the shred-registry
  identity (exact, no hashing — a DEK is 32 random bytes). `unwrap_dek`
  checks the shred set first → `nullopt`. `InMemoryKeyProvider` carries a
  `std::set<std::string> shredded_`. `forget_kek_version()` kept as the
  coarse "retire a whole KEK version" case, distinct from per-DEK shred.
- `Crypto/runtime/harpia_key_provider_local.h` — `LocalKeyProvider::shred_dek`
  appends `<kek_version> <hex(bytes)>` to a `<storage_path>.shred`
  append-only sidecar (there is no un-shred); the ctor's `load_shreds()`
  reads it back. The KEK store file is never rewritten by a shred.
- `UnitTests/test_crypto_shred.py` — 5 g++-gated tests (`-Werror`), both
  providers: shred makes only that record unrecoverable (KEK + caller's
  `WrappedDek` untouched), per-DEK, idempotent + irreversible
  (`static_assert` no `unshred_dek`; rotation doesn't resurrect),
  `LocalKeyProvider` shred survives a restart and doesn't rewrite the KEK
  store.
- Additive — no generator code touched, no golden impact. Host 178 passed;
  full Docker suite 250 passed, 4 skipped.
