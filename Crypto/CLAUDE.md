# Crypto — CryptoBackend selection point (F5) + KeyProvider runtime (the key-management epic)

**Pipeline role:** Cross-cutting. Two pieces:
1. **F5 — `CryptoBackend`** (`backend.py`), Python, generation-time only.
   Mirrors `Database/backends/` one level up in abstraction: `DbBackend`
   answers "which SQL dialect", `CryptoBackend` answers "which crypto
   module" (standard vs. FIPS-validated OpenSSL). Resolved once per run
   (`main.py`, mirrored in `UnitTests/run_pipeline.py`), logged, persisted
   as build metadata. See the F5 section of
   `Initiatives/medical_devices/epics/foundation-handoff.md`.
2. **the key-management epic — `KeyProvider`** (`runtime/harpia_key_provider*.h`),
   hand-written C++, copied verbatim into a *generated project*'s output
   (the db-encryption epic is the first consumer — `Database/CrudlAdapter.py` copies
   `harpia_encrypted_column.h` + `harpia_key_provider.h` +
   `harpia_audit_sink.h` into `generated/cpp/crypto/` for `phi`-column
   DAOs) — same pattern as
   `Compliance/runtime/harpia_audit_sink.h` /
   `Compliance/runtime/harpia_delivery.h`. **the key-management epic is complete (all tasks).**
   **key-management task 1** = the interface + envelope shape + an in-memory dummy. **key-management task 2** =
   `LocalKeyProvider`, the default no-KMS backend: file-persisted KEKs + a
   fail-safe acknowledgment gate. **key-management task 3** = `shred_dek()` per-DEK
   crypto-shred (`unwrap_dek` → `nullopt`, KEK untouched; `<store>.shred`
   append-only sidecar in `LocalKeyProvider`). **key-management task 4** = zeroization
   (`detail::secure_zero`, `Dek`'s destructor, KEK wipe on eviction) +
   `AuditSink` wiring (every key op → `record("key_<op>", "kek:<v>"|"dek")`;
   never key bytes). **key-management task 5** = `harpia_key_provider_kms.h`: the `KmsClient`
   extension seam + `KmsKeyProvider` (routes every op to the seam, adds
   nothing) + `MockKms` reference impl — the structural proof that swapping
   backends needs no interface change. All still placeholder XOR: the real
   cipher lands when a backend is bound to the F5 seam. See
   `Initiatives/medical_devices/epics/key-management/`.

**F5's first real consumer: DDS-Security (dds-transport task 3).** the
key-management epic's `KeyProvider` links against the F5 seam for a *real*
cipher, but key-management tasks 1–5 do no actual crypto (placeholder XOR);
the transport-authn epic (mTLS stack) still hasn't started. `DdsAdapter`
(task 3) is the first code to actually read the seam for *transport* crypto:
it records `CryptoBackend.transport_security()` + whether the compliance
profile mandates hardened transport into
`generated/cpp/dds/security/dds_security_selection.json`, and its
`harpia_dds_security.h` wires the OpenSSL-backed Cyclone DDS-Security builtin
plugins. The seam was extended for this — see `transport_security()` /
`transport_hardening_required()` below — so the transport-authn epic's mTLS
work keys off the same descriptor and predicate and the two can't drift onto
different modules or diverge on when hardening is mandatory.
**Entry points (F5):** `get_backend(name=None, compliance=None)` ->
`CryptoBackend`; `write_build_metadata(backend, dest)` -> path to the
written sidecar; `register(backend)` (extension point for a later real
HSM-backed backend); `transport_hardening_required(compliance)` -> bool
(`risk_class == CLASS_C` or `topology == CLOUD_CONNECTED`, §0a — the one
predicate `get_backend()` itself now keys the FIPS default off);
`CryptoBackend.transport_security()` -> `{cmake_package, openssl_provider,
fips}` descriptor for transport-security consumers.
**Entry points (the key-management epic):** `harpia::crypto::KeyProvider` (C++ ABC:
`active_kek_version` / `generate_dek` / `wrap_dek` / `unwrap_dek` ->
`std::optional<Dek>` / `rotate` / `shred_dek`); `shred_key(w)`,
`detail::secure_zero(s)`, `detail::random_bytes(n)`, the `kOp*` operation
strings; `InMemoryKeyProvider` (key-management task 1); `LocalKeyProvider` +
`LocalKeyProviderConfig` + `LocalKeyProviderRefused` +
`local_key_provider_acknowledged()` (key-management task 2); `KmsClient` (the seam) +
`KmsKeyProvider` + `MockKms` (key-management task 5). Every provider ctor takes a trailing
defaulted `compliance::AuditSink&` (key-management task 4).
`Crypto.key_provider_common` holds the `*_RUNTIME_SRC` path constants +
`*_DEPS` co-copy tuples (`harpia_key_provider.h` → `harpia_audit_sink.h`;
the backends → `harpia_key_provider.h` + its deps), mirroring
`Compliance.audit_common` / `Compliance.delivery_common`.

## Files
- `backend.py` — `CryptoBackend` (ABC: `cmake_package`, `openssl_provider`,
  `transport_security()` -> descriptor dict, `sbom_entry()` -- which now
  carries a `"transport_security"` key), two concrete stubs
  (`StandardOpenSSLBackend` / `FipsOpenSSLBackend`, name+fips only -- no
  actual crypto operations exist anywhere in this repo to implement yet),
  the `_REGISTRY`/`_ALIASES` singleton registry + `get_backend()`/
  `register()` (identical shape to `Database/backends/__init__.py`), the
  module-level `transport_hardening_required(compliance)` predicate (§0a --
  `get_backend()` factors its own FIPS-default check through it), and
  `write_build_metadata()`.
- `runtime/harpia_key_provider.h` — the key-management epic.
  `harpia::crypto`: `detail::secure_zero` / `detail::random_bytes`, `Dek`
  (`seal`/`open` — DEK-only touches the value; XOR placeholder; **key-management task 4**
  zeroizing destructor), `WrappedDek`, `shred_key(w)`, the `kOp*` operation
  strings, `KeyProvider` ABC (`…/rotate/shred_dek`), `InMemoryKeyProvider`
  (DUMMY, in-process). Envelope encryption baked in: KEK only wraps DEKs;
  `rotate()` is O(keys). `unwrap_dek` → `nullopt` for an
  unknown/forgotten/**shredded** DEK (Rule 5). `shred_dek(w)` (key-management task 3):
  permanent, irreversible, per-DEK — the right-to-erasure mechanism.
  **key-management task 4:** ctor takes a defaulted `AuditSink&`; every op is recorded;
  KEKs zeroized on eviction + in the destructor. Not thread-safe.
- `runtime/harpia_key_provider_local.h` — the key-management epic (+ key-management task 3 shred
  sidecar, + key-management task 4 audit/zeroize). The default no-KMS backend.
  `LocalKeyProvider` persists KEK material to
  `LocalKeyProviderConfig::storage_path` (survives a restart).
  **Fail-safe gate:** ctor throws `LocalKeyProviderRefused` when
  `phi_at_scale && !acknowledged`; opt in via
  `local_key_provider_acknowledged()` (reads `HARPIA_ACK_LOCAL_KEY_PROVIDER`)
  or the config field. Shred → `<storage_path>.shred` append-only sidecar,
  never rewrites the KEK store. `#include`s `harpia_key_provider.h`.
- `runtime/harpia_key_provider_kms.h` — the key-management epic. The KMS/HSM
  extension point. `KmsClient` (the tiny seam an integrator implements for
  AWS KMS / Vault / a PKCS#11 HSM — four ops over opaque bytes + an
  integer version); `KmsKeyProvider` (routes every `KeyProvider` op to the
  seam, adds nothing — the "no interface change to swap backends" proof;
  per-DEK shred is a local set since most KMS only delete whole versions);
  `MockKms` (in-header reference `KmsClient`, in-memory, XOR — ships like
  `NoOpAuditSink`). Takes an `AuditSink&` (key-management task 4). `#include`s
  `harpia_key_provider.h`.
- `runtime/harpia_encrypted_column.h` — the db-encryption epic. `harpia::crypto`:
  `encrypt_field(KeyProvider&, plaintext)` (generate_dek → seal → wrap_dek
  → frame `{kek_version, wrapped_dek, ciphertext}` → `"enc:v1:"` + hex, so
  a `phi` value stays in its column's existing TEXT type), `decrypt_field`
  + `decrypt_field_{ll,int,double}` (numeric `phi` fields; an unrecoverable
  value → 0/"", never a throw — Rule 5), `default_key_provider()` (a
  process-wide `InMemoryKeyProvider` so a generated DAO ctor can default
  its `KeyProvider&`). Adds no crypto of its own — frames + routes; the
  real AEAD is the F5-seam binding. `#include`s `harpia_key_provider.h`.
- `key_provider_common.py` — `KEY_PROVIDER_RUNTIME` / `_SRC` (key-management task 1) +
  `KEY_PROVIDER_RUNTIME_DEPS` (key-management task 4: → `harpia_audit_sink.h`);
  `KEY_PROVIDER_LOCAL_RUNTIME` (key-management task 2) + `KEY_PROVIDER_KMS_RUNTIME` (key-management task 5) +
  `ENCRYPTED_COLUMN_RUNTIME` (db-encryption task 1), each with `_SRC` + a `_DEPS` that
  includes `harpia_key_provider.h` and its deps transitively. **Consumed
  by `Database/CrudlAdapter.py`** — when a message has a `phi` column it
  `copy_if_different`s the whole set (`ENCRYPTED_COLUMN_RUNTIME` + the key-management task 1
  interface + `harpia_audit_sink.h` (db-encryption task 1), plus `KEY_PROVIDER_LOCAL_RUNTIME`
  and `KEY_PROVIDER_KMS_RUNTIME` (db-encryption task 2, so a deployment can hand the DAO a
  real persistent KeyProvider)) into `generated/cpp/crypto/`.

## Key facts / gotchas
- **Selection order in `get_backend()`:** explicit `name` (e.g.
  `HARPIA_CRYPTO_BACKEND` env var, same convention as
  `HARPIA_DB_BACKEND`) wins outright; otherwise, if
  `transport_hardening_required(compliance)` (`risk_class == CLASS_C` or
  `topology == CLOUD_CONNECTED`, §0a's "one project-wide floor" -- never
  per-jurisdiction), the FIPS backend; otherwise `DEFAULT_BACKEND`
  ("openssl"). Unknown name -> `ValueError`, same
  hard-fail-at-generation-time convention as
  `Database.backends.get_backend`. `transport_hardening_required()` is the
  single source of truth for that predicate so DDS-Security (dds-transport
  task 3) and the transport-authn epic's mTLS default-on off the exact same
  rule.
- **`transport_security()` vs `transport_hardening_required()`:** the first
  is *which* module (backend-derived: `cmake_package` / `openssl_provider` /
  `fips`); the second is *whether* a project must harden its transport
  (compliance-derived). DDS-Security's `dds_security_selection.json` records
  both. Keep them separate -- a project can be on the FIPS backend without
  `risk_class == CLASS_C` (explicit `HARPIA_CRYPTO_BACKEND`), and "FIPS" is
  not the same statement as "mTLS/DDS-Security mandatory".
- **Backends are stateless singletons, provably shared** -- `get_backend()`
  returns the identical object across calls (`_REGISTRY` is built once at
  import time). This is what makes "the key-management epic and the transport-authn epic provably use the
  same crypto module within one build" (F5's stated guarantee) trivially
  true once both actually call through this seam: they get the same
  object, not two independently-constructed ones that merely compare equal.
- **`write_build_metadata()` writes `<dest>/build_metadata/crypto_backend.json`**
  via `Util.util.write_if_different` (mtime-preserving, same convention as
  every other generated artifact). Nothing reads this back yet -- the process-artifacts epic
  (`ComplianceReport/`, SBOM emission) doesn't exist in this repo either --
  but F5's own guarantee is that the choice gets recorded, not that
  something consumes the record yet. `main.py` calls this unconditionally,
  same place it logs "Crypto backend: ...".
- Depends on `Compliance.context` (`RiskClass`, `Topology`) for the
  compliance-driven default -- a one-directional dependency (`Crypto` ->
  `Compliance`), no cycle.

## Touchpoints
- Called by: `main.py`, `UnitTests/run_pipeline.py` (F5's `backend.py`) --
  both resolve the `CryptoBackend` once and now also hand it to
  `DdsAdapter(crypto_backend=…)` (dds-transport task 3), the same pattern as
  `CrudlAdapter(backend=dbBackend)`. `DdsAdapter` reads
  `transport_security()` + `transport_hardening_required()` for
  `dds/security/dds_security_selection.json`.
  `runtime/harpia_key_provider.h` + `runtime/harpia_encrypted_column.h` are
  `copy_if_different`'d into `generated/cpp/crypto/` by
  `Database/CrudlAdapter.py` (the db-encryption epic) for any message with a `phi`
  column, via `Crypto.key_provider_common`.
- Depends on: `Compliance.context`, `Util.util.write_if_different` (F5);
  C++ standard library only for the key-management task 1 / db-encryption task 1 runtime headers.
- Tested by: `UnitTests/test_crypto_backend.py` (F5 -- including
  `transport_security()` tracking the backend and
  `transport_hardening_required()` following `risk_class`/`topology`);
  `UnitTests/test_dds_security.py` (dds-transport task 3 -- the first
  transport consumer of the seam);
  `UnitTests/test_key_provider.py` (key-management task 1), `test_local_key_provider.py`
  (key-management task 2), `test_crypto_shred.py` (key-management task 3), `test_key_provider_audit.py`
  (key-management task 4), `test_kms_key_provider.py` (key-management task 5) — the the key-management tasks ones g++-gated and
  compiled with `-I Compliance/runtime` (for `harpia_audit_sink.h`);
  `test_stage8_db.py`'s `test_a1_*` (db-encryption task 1, `harpia_encrypted_column.h` +
  CrudlAdapter phi encrypt-on-write / decrypt-on-read).
