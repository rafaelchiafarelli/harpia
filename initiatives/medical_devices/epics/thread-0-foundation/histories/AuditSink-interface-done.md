
### F3 — AuditSink interface (stub)

**Status: done (2026-08-23), on `feature/thread-0-foundation`, not yet
merged to `main`.** Implemented as hand-written C++, not Python --
`Compliance/runtime/harpia_audit_sink.h` (`AuditSink` abstract interface +
`NoOpAuditSink` + `default_audit_sink()` shared instance), copied verbatim
into a generated project the same way `Capability/runtime/
harpia_capability_dispatch.h` already is, not a Python abstraction like F1's
`ComplianceContext` -- it's *generated* code (Track A's DAOs, Track C's
transports, ...) that will call `record()` at runtime, not harpia's Python
generator. `Compliance/audit_common.py` adds the path constant mirroring
`Capability/capability_common.py`; no adapter copies the header into output
yet since nothing consumes it (Track A/C haven't started) -- that's next
tracks' job, per this task's own "documented injection point for
downstream tracks" scope.

One design decision resolved during implementation, undocumented anywhere
in the plan corpus: `record(operation, subject, detail="")` takes a plain
`std::string operation` rather than a Foundation-owned closed enum, because
the vocabulary spans DB ops, key ops, transport events, and delivery-queue
events across five+ independent downstream tracks that shouldn't have to
touch this Foundation header to add their own operation name (see
`Compliance/CLAUDE.md`'s "Key facts" for the full reasoning). `subject`/
`detail` are identifying metadata only, never a field's actual value, per
design-rules doc Rule 5 -- enforced structurally by the signature, not by
convention.

All tests pass (`tests/test_audit_sink.py`, g++-gated, no generated project
needed); full Docker toolchain suite shows no new failures.

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