
### F3 — AuditSink interface (stub)
- **Deliverables:** abstract `AuditSink` interface + `NoOpAuditSink`
  default implementation; documented injection point for downstream tracks.
- **Guarantees:** interface compiles and instantiates standalone; no-op
  implementation has zero side effects.
- **Out of scope:** the real, tamper-evident implementation — built once
  per project, gated by `risk_class`, not per jurisdiction (§0a).
- **Tests:**
  - Unit: `NoOpAuditSink.record()` called, asserts no side effect, no crash.
  - Integration: instantiate and inject into a dummy generated class,
    confirm no build/runtime error.

### F4 — Regression baseline
- **Deliverables:** tagged, CI-recorded green baseline of the existing
  test suite.
- **Guarantees:** every subsequent track's acceptance gate refers back to
  this exact baseline.