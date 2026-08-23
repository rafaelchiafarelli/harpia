### F5 — CryptoBackend selection point

**Status: done (2026-08-23), on `feature/thread-0-foundation`, not yet
merged to `main`.** Implemented as `Crypto/backend.py`, mirroring
`Database/backends/` exactly one level up in abstraction (`DbBackend`
answers "which SQL dialect", `CryptoBackend` answers "which crypto
module"): an ABC (`cmake_package`, `openssl_provider`, `sbom_entry()`),
two stub backends (`StandardOpenSSLBackend`/`FipsOpenSSLBackend` -- name
and metadata only, no real crypto operations exist anywhere in this repo
yet to abstract over), and a `_REGISTRY`/`get_backend()` singleton
resolver identical in shape to `Database.backends.get_backend`. Selection
order: explicit name (`HARPIA_CRYPTO_BACKEND` env var) wins outright;
otherwise `risk_class == CLASS_C` or `topology == CLOUD_CONNECTED` (from
`ComplianceContext`) defaults to the FIPS backend; otherwise plain
`"openssl"`. `write_build_metadata()` persists the choice to
`<dest>/build_metadata/crypto_backend.json` (write-if-different) for
Track M's SBOM to read once it exists -- nothing reads it back today, same
as F3's `AuditSink` having no real caller yet.

Neither of the two tracks this seam exists to keep in sync (Track O
key-management, Track C transport/TLS) has started in this repo, so "Track
O and Track C provably use the same crypto module" is verified at the seam
itself: `get_backend()` returns the identical singleton across calls,
exactly like `Database.backends.get_backend` already does -- whichever
track calls it first and second get the same object, not two independently
constructed ones that merely compare equal. `main.py`/`tests/run_pipeline.py`
both resolve and log the backend and write the metadata sidecar
unconditionally, even though nothing else consumes it yet.

All tests pass (`tests/test_crypto_backend.py`); golden baseline and full
Docker toolchain suite confirmed unaffected (the metadata sidecar lands
under `build_metadata/`, never collected into any snapshotted directory).

- **Deliverables:** a single compile-time seam (build flag/CMake option),
  driven by `risk_class`/`topology`, choosing which underlying crypto
  module a build links against. Both Track O and Track C consume this
  same seam — neither independently links its own crypto module. One
  selection per project, never per jurisdiction (§0a).
- **Guarantees:** exactly one crypto module is linked per project; Track O
  and Track C provably use the same one; the choice made is recorded as
  build metadata for Track M's SBOM.
- **Out of scope:** doesn't ship or validate the crypto modules themselves
  — just the seam.
- **Tests:**
  - Unit: build-flag selection actually changes which module gets linked.
  - Integration: build against each supported crypto module, confirm
    Track O and Track C work identically against each.
  - Acceptance gate: a direct assertion that Track O and Track C agree on
    which crypto module is linked within the same build (no cross-variant
    diff job needed — Track N's was dropped per §0a, one code path).
