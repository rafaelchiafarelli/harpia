## Session O.1 — `KeyProvider` interface + envelope-encryption shape

Landed in `b6bedda`.

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

### Landed as

- `Crypto/runtime/harpia_key_provider.h` — hand-written C++ (not generated),
  same pattern as `harpia_audit_sink.h` / `harpia_delivery.h`.
  `harpia::crypto`: `Dek` (`seal`/`open` — the DEK, and only the DEK,
  touches the value), `WrappedDek` (`kek_version` + `bytes`), `KeyProvider`
  ABC (`active_kek_version` / `generate_dek` / `wrap_dek` / `unwrap_dek` →
  `std::optional<Dek>` / `rotate` → new version), and `InMemoryKeyProvider`
  — an in-memory, non-persistent DUMMY (XOR transforms, NOT crypto) for
  this session's and downstream tracks' tests until O.2's real backend.
  `unwrap_dek` returns an empty optional for an unknown/forgotten KEK
  version (Rule 5 — distinct observable outcome; also the O.3 crypto-shred
  path, exercised early via `forget_kek_version()`).
- `Crypto/key_provider_common.py` — `KEY_PROVIDER_RUNTIME` /
  `KEY_PROVIDER_RUNTIME_SRC` path constants (mirror `audit_common.py` /
  `delivery_common.py`). No adapter copies the header yet — Track A is the
  first consumer.
- `UnitTests/test_key_provider.py` — 8 g++-gated tests (`-Werror`):
  wrap/unwrap round trip, `seal`/`open` (survives a DEK wrap/unwrap in
  between), `WrappedDek` records the active KEK version, rotation bumps the
  version and old DEKs still unwrap, rotation mutates no existing
  `WrappedDek`, unknown/forgotten KEK version → `nullopt`, polymorphic use
  through `KeyProvider&`.
- No generator code touched; no golden impact.
