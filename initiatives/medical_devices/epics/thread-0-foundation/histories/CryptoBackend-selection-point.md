### F5 — CryptoBackend selection point
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
