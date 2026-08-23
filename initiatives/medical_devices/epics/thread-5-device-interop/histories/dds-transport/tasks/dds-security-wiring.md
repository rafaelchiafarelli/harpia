
## Session P.3 — DDS-Security wiring

- **Depends on:** P.2 merged; F5 (Foundation).
- **Deliverable:** OMG DDS-Security (authentication/access-control/
  encryption plugins) compiled in via the F5 `CryptoBackend` seam, one
  selection per project driven by `risk_class`/`topology` (never per
  jurisdiction, `harpia_medical_master_plan.md` §0a) — same posture as
  Track C's mTLS and Track B's CURVE.
- **Guarantees:** plaintext/unauthenticated DDS refused by default when
  the compliance profile requires it.
- **Out of scope, by decision:** LGPD Art. 33 / Art. 11 §4 constraints on
  where a `phi`-tagged message publishing off the bus is allowed to go
  are deployment topology and legal review, not something this track
  enforces at compile time or runtime.
- **Tests:**
  - Integration: extend P.2's DDS demo with DDS-Security enabled, confirm
    unauthenticated peers are refused.