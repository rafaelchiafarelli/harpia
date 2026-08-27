# Crypto — CryptoBackend selection point (F5) + KeyProvider runtime (Track O)

**Pipeline role:** Cross-cutting. Two pieces:
1. **F5 — `CryptoBackend`** (`backend.py`), Python, generation-time only.
   Mirrors `Database/backends/` one level up in abstraction: `DbBackend`
   answers "which SQL dialect", `CryptoBackend` answers "which crypto
   module" (standard vs. FIPS-validated OpenSSL). Resolved once per run
   (`main.py`, mirrored in `UnitTests/run_pipeline.py`), logged, persisted
   as build metadata. See the F5 section of
   `Initiatives/medical_devices/epics/handoff-document.md`.
2. **Track O — `KeyProvider`** (`runtime/harpia_key_provider*.h`),
   hand-written C++, copied verbatim into a *generated project*'s output
   later (Track A is the first consumer) — same pattern as
   `Compliance/runtime/harpia_audit_sink.h` /
   `Compliance/runtime/harpia_delivery.h`. **Track O is complete (O.1–O.5).**
   **O.1** = the interface + envelope shape + an in-memory dummy. **O.2** =
   `LocalKeyProvider`, the default no-KMS backend: file-persisted KEKs + a
   fail-safe acknowledgment gate. **O.3** = `shred_dek()` per-DEK
   crypto-shred (`unwrap_dek` → `nullopt`, KEK untouched; `<store>.shred`
   append-only sidecar in `LocalKeyProvider`). **O.4** = zeroization
   (`detail::secure_zero`, `Dek`'s destructor, KEK wipe on eviction) +
   `AuditSink` wiring (every key op → `record("key_<op>", "kek:<v>"|"dek")`;
   never key bytes). **O.5** = `harpia_key_provider_kms.h`: the `KmsClient`
   extension seam + `KmsKeyProvider` (routes every op to the seam, adds
   nothing) + `MockKms` reference impl — the structural proof that swapping
   backends needs no interface change. All still placeholder XOR: the real
   cipher lands when a backend is bound to the F5 seam. See
   `Initiatives/medical_devices/epics/thread-1-data-and-keys/histories/key-management/`.

**F5's real consumers still don't exist:** Track O's `KeyProvider` links
against the F5 seam for a *real* cipher, but O.1–O.5 do no actual crypto
(placeholder XOR). Track C (TLS stack) hasn't started.
**Entry points (F5):** `get_backend(name=None, compliance=None)` ->
`CryptoBackend`; `write_build_metadata(backend, dest)` -> path to the
written sidecar; `register(backend)` (extension point for a later real
HSM-backed backend).
**Entry points (Track O):** `harpia::crypto::KeyProvider` (C++ ABC:
`active_kek_version` / `generate_dek` / `wrap_dek` / `unwrap_dek` ->
`std::optional<Dek>` / `rotate` / `shred_dek`); `shred_key(w)`,
`detail::secure_zero(s)`, `detail::random_bytes(n)`, the `kOp*` operation
strings; `InMemoryKeyProvider` (O.1); `LocalKeyProvider` +
`LocalKeyProviderConfig` + `LocalKeyProviderRefused` +
`local_key_provider_acknowledged()` (O.2); `KmsClient` (the seam) +
`KmsKeyProvider` + `MockKms` (O.5). Every provider ctor takes a trailing
defaulted `compliance::AuditSink&` (O.4).
`Crypto.key_provider_common` holds the `*_RUNTIME_SRC` path constants +
`*_DEPS` co-copy tuples (`harpia_key_provider.h` → `harpia_audit_sink.h`;
the backends → `harpia_key_provider.h` + its deps), mirroring
`Compliance.audit_common` / `Compliance.delivery_common`.

## Files
- `backend.py` — `CryptoBackend` (ABC: `cmake_package`, `openssl_provider`,
  `sbom_entry()`), two concrete stubs (`StandardOpenSSLBackend` /
  `FipsOpenSSLBackend`, name+fips only -- no actual crypto operations exist
  anywhere in this repo to implement yet), the `_REGISTRY`/`_ALIASES`
  singleton registry + `get_backend()`/`register()` (identical shape to
  `Database/backends/__init__.py`), and `write_build_metadata()`.
- `runtime/harpia_key_provider.h` — Track O / O.1 + O.3 + O.4.
  `harpia::crypto`: `detail::secure_zero` / `detail::random_bytes`, `Dek`
  (`seal`/`open` — DEK-only touches the value; XOR placeholder; **O.4**
  zeroizing destructor), `WrappedDek`, `shred_key(w)`, the `kOp*` operation
  strings, `KeyProvider` ABC (`…/rotate/shred_dek`), `InMemoryKeyProvider`
  (DUMMY, in-process). Envelope encryption baked in: KEK only wraps DEKs;
  `rotate()` is O(keys). `unwrap_dek` → `nullopt` for an
  unknown/forgotten/**shredded** DEK (Rule 5). `shred_dek(w)` (O.3):
  permanent, irreversible, per-DEK — the right-to-erasure mechanism.
  **O.4:** ctor takes a defaulted `AuditSink&`; every op is recorded;
  KEKs zeroized on eviction + in the destructor. Not thread-safe.
- `runtime/harpia_key_provider_local.h` — Track O / O.2 (+ O.3 shred
  sidecar, + O.4 audit/zeroize). The default no-KMS backend.
  `LocalKeyProvider` persists KEK material to
  `LocalKeyProviderConfig::storage_path` (survives a restart).
  **Fail-safe gate:** ctor throws `LocalKeyProviderRefused` when
  `phi_at_scale && !acknowledged`; opt in via
  `local_key_provider_acknowledged()` (reads `HARPIA_ACK_LOCAL_KEY_PROVIDER`)
  or the config field. Shred → `<storage_path>.shred` append-only sidecar,
  never rewrites the KEK store. `#include`s `harpia_key_provider.h`.
- `runtime/harpia_key_provider_kms.h` — Track O / O.5. The KMS/HSM
  extension point. `KmsClient` (the tiny seam an integrator implements for
  AWS KMS / Vault / a PKCS#11 HSM — four ops over opaque bytes + an
  integer version); `KmsKeyProvider` (routes every `KeyProvider` op to the
  seam, adds nothing — the "no interface change to swap backends" proof;
  per-DEK shred is a local set since most KMS only delete whole versions);
  `MockKms` (in-header reference `KmsClient`, in-memory, XOR — ships like
  `NoOpAuditSink`). Takes an `AuditSink&` (O.4). `#include`s
  `harpia_key_provider.h`.
- `key_provider_common.py` — `KEY_PROVIDER_RUNTIME` / `_SRC` (O.1) +
  `KEY_PROVIDER_RUNTIME_DEPS` (O.4: → `harpia_audit_sink.h`);
  `KEY_PROVIDER_LOCAL_RUNTIME` (O.2) + `KEY_PROVIDER_KMS_RUNTIME` (O.5),
  each with `_SRC` + a `_DEPS` that includes `harpia_key_provider.h` and
  its deps transitively. No adapter copies any of these yet (Track A will).

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
  `UnitTests/test_key_provider.py` (O.1), `test_local_key_provider.py`
  (O.2), `test_crypto_shred.py` (O.3), `test_key_provider_audit.py`
  (O.4), `test_kms_key_provider.py` (O.5) — the O.* ones g++-gated and
  compiled with `-I Compliance/runtime` (for `harpia_audit_sink.h`).
