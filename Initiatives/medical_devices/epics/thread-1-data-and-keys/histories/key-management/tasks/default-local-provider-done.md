## Session O.2 — Default local `KeyProvider` + fail-safe acknowledgment gate

Landed in `cc26db4`.

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

### Landed as

- `Crypto/runtime/harpia_key_provider_local.h` — `LocalKeyProvider :
  public KeyProvider`. KEK material persisted to
  `LocalKeyProviderConfig::storage_path` (a file), loaded on construction,
  rewritten on `rotate()` — keys survive a restart (the difference from
  O.1's `InMemoryKeyProvider`). Ctor throws `LocalKeyProviderRefused` when
  `phi_at_scale && !acknowledged`. `local_key_provider_acknowledged()`
  reads `HARPIA_ACK_LOCAL_KEY_PROVIDER` (`1`/`true`/`yes`, any case) as a
  convenience source for the `acknowledged` field. Cipher is still O.1's
  placeholder XOR — the real AES-KW/GCM lands when bound to the F5
  `CryptoBackend` seam.
- `Crypto/key_provider_common.py` — `KEY_PROVIDER_LOCAL_RUNTIME` / `_SRC`
  + `_DEPS` (names `harpia_key_provider.h` as a co-copy).
- `UnitTests/test_local_key_provider.py` — 7 g++-gated tests (`-Werror`):
  contract conformance, KEK persistence across instances, rotation
  persisted, the acknowledgment gate (refused / acknowledged / not at
  scale), the env helper.
- Additive — no generator code touched, no golden impact. Host 173 passed;
  full Docker suite 245 passed, 4 skipped.
- **Deferred:** the compliance profile that sets `phi_at_scale` is wired
  from `ComplianceContext` at generation time by **Track A** (first
  consumer to copy these headers into generated output); O.2 supplies the
  config bool directly.
