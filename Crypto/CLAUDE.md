# Crypto — CryptoBackend selection point (F5) + KeyProvider runtime (Track O)

**Pipeline role:** Cross-cutting. Two pieces:
1. **F5 — `CryptoBackend`** (`backend.py`), Python, generation-time only.
   Mirrors `Database/backends/` one level up in abstraction: `DbBackend`
   answers "which SQL dialect", `CryptoBackend` answers "which crypto
   module" (standard vs. FIPS-validated OpenSSL). Resolved once per run
   (`main.py`, mirrored in `UnitTests/run_pipeline.py`), logged, persisted
   as build metadata. See the F5 section of
   `Initiatives/medical_devices/epics/handoff-document.md`.
2. **Track O / O.1 — `KeyProvider`** (`runtime/harpia_key_provider.h`),
   hand-written C++, copied verbatim into a *generated project*'s output
   later (Track A is the first consumer) — same pattern as
   `Compliance/runtime/harpia_audit_sink.h` /
   `Compliance/runtime/harpia_delivery.h`. Interface + envelope shape + an
   in-memory dummy only; the real backends are O.2 (local default) and O.5
   (KMS/HSM adapter). See
   `Initiatives/medical_devices/epics/thread-1-data-and-keys/histories/key-management/`.

**F5's real consumers still don't exist:** Track O's `KeyProvider` links
against the F5 seam for its *real* backend (O.2+), but O.1 is the interface
only and does no actual crypto. Track C (TLS stack) hasn't started.
**Entry points (F5):** `get_backend(name=None, compliance=None)` ->
`CryptoBackend`; `write_build_metadata(backend, dest)` -> path to the
written sidecar; `register(backend)` (extension point for a later real
HSM-backed backend).
**Entry points (O.1):** `harpia::crypto::KeyProvider` (C++ ABC:
`active_kek_version` / `generate_dek` / `wrap_dek` / `unwrap_dek` ->
`std::optional<Dek>` / `rotate`); `harpia::crypto::InMemoryKeyProvider`
(the dummy). `Crypto.key_provider_common.KEY_PROVIDER_RUNTIME_SRC` is the
path constant, mirroring `Compliance.audit_common` /
`Compliance.delivery_common`.

## Files
- `backend.py` — `CryptoBackend` (ABC: `cmake_package`, `openssl_provider`,
  `sbom_entry()`), two concrete stubs (`StandardOpenSSLBackend` /
  `FipsOpenSSLBackend`, name+fips only -- no actual crypto operations exist
  anywhere in this repo to implement yet), the `_REGISTRY`/`_ALIASES`
  singleton registry + `get_backend()`/`register()` (identical shape to
  `Database/backends/__init__.py`), and `write_build_metadata()`.
- `runtime/harpia_key_provider.h` — Track O / O.1. `harpia::crypto`:
  `Dek` (`seal`/`open` — the DEK, and only the DEK, touches the value;
  dummy XOR transform), `WrappedDek` (`kek_version` + `bytes`),
  `KeyProvider` ABC, `InMemoryKeyProvider` (in-memory, non-persistent,
  DUMMY — for tests / downstream tracks until O.2). Envelope encryption
  baked in: KEK only wraps DEKs; `rotate()` mints a new KEK version and
  touches no existing `WrappedDek` or ciphertext (O(keys), not O(data)).
  `unwrap_dek` → `nullopt` for an unknown/forgotten KEK version (Rule 5;
  also the O.3 crypto-shred path). Not thread-safe (caller-synchronized).
- `key_provider_common.py` — `KEY_PROVIDER_RUNTIME` / `_SRC` path
  constants. No adapter copies the header yet (Track A will). No co-copy
  DEPS tuple — the header has no harpia-internal includes; O.4 adds one if
  it pulls in `harpia_audit_sink.h`.

## Key facts / gotchas
- **Selection order in `get_backend()`:** explicit `name` (e.g.
  `HARPIA_CRYPTO_BACKEND` env var, same convention as
  `HARPIA_DB_BACKEND`) wins outright; otherwise, if `compliance` is given,
  `risk_class == CLASS_C` or `topology == CLOUD_CONNECTED` defaults to the
  FIPS backend (§0a's "one project-wide floor" -- never per-jurisdiction);
  otherwise `DEFAULT_BACKEND` ("openssl"). Unknown name -> `ValueError`,
  same hard-fail-at-generation-time convention as
  `Database.backends.get_backend`.
- **Backends are stateless singletons, provably shared** -- `get_backend()`
  returns the identical object across calls (`_REGISTRY` is built once at
  import time). This is what makes "Track O and Track C provably use the
  same crypto module within one build" (F5's stated guarantee) trivially
  true once both actually call through this seam: they get the same
  object, not two independently-constructed ones that merely compare equal.
- **`write_build_metadata()` writes `<dest>/build_metadata/crypto_backend.json`**
  via `Util.util.write_if_different` (mtime-preserving, same convention as
  every other generated artifact). Nothing reads this back yet -- Track M
  (`ComplianceReport/`, SBOM emission) doesn't exist in this repo either --
  but F5's own guarantee is that the choice gets recorded, not that
  something consumes the record yet. `main.py` calls this unconditionally,
  same place it logs "Crypto backend: ...".
- Depends on `Compliance.context` (`RiskClass`, `Topology`) for the
  compliance-driven default -- a one-directional dependency (`Crypto` ->
  `Compliance`), no cycle.

## Touchpoints
- Called by: `main.py`, `UnitTests/run_pipeline.py` (F5's `backend.py`).
  `runtime/harpia_key_provider.h` is not consumed by any adapter yet —
  Track A will `copy_if_different` it into generated output via
  `Crypto.key_provider_common`.
- Depends on: `Compliance.context`, `Util.util.write_if_different` (F5);
  C++ standard library only for the O.1 runtime header.
- Tested by: `UnitTests/test_crypto_backend.py` (F5),
  `UnitTests/test_key_provider.py` (O.1, g++-gated).
