# Crypto — CryptoBackend selection point (Foundation F5)

**Pipeline role:** Cross-cutting, generation-time only. Mirrors
`Database/backends/` one level up in abstraction: `DbBackend` answers
"which SQL dialect", `CryptoBackend` answers "which crypto module" (e.g.
standard vs. FIPS-validated OpenSSL). Resolved once per run (`main.py`,
mirrored in `UnitTests/run_pipeline.py`), logged, and persisted as build
metadata. See the F5 section of
`Initiatives/medical_devices/epics/handoff-document.md` (the Foundation
thread itself was merged to `dev` and removed; see git history for the
original implementation write-up).
**Neither real consumer exists in this repo yet** -- Track O (key-wrap/
envelope-encryption) and Track C (TLS stack), the two tracks this seam
exists to keep in sync, haven't started. F5 is the seam only, same "no
implementation yet" scope as F3's `AuditSink`.
**Entry points:** `get_backend(name=None, compliance=None)` ->
`CryptoBackend`; `write_build_metadata(backend, dest)` -> path to the
written sidecar; `register(backend)` (extension point for a later real
HSM-backed backend).

## Files
- `backend.py` — `CryptoBackend` (ABC: `cmake_package`, `openssl_provider`,
  `sbom_entry()`), two concrete stubs (`StandardOpenSSLBackend` /
  `FipsOpenSSLBackend`, name+fips only -- no actual crypto operations exist
  anywhere in this repo to implement yet), the `_REGISTRY`/`_ALIASES`
  singleton registry + `get_backend()`/`register()` (identical shape to
  `Database/backends/__init__.py`), and `write_build_metadata()`.

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
- Called by: `main.py`, `UnitTests/run_pipeline.py`.
- Depends on: `Compliance.context`, `Util.util.write_if_different`.
- Tested by: `UnitTests/test_crypto_backend.py`.
