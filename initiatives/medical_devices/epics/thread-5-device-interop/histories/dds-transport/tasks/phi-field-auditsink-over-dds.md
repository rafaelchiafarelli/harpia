## Session P.4 — `phi` field `AuditSink` wiring over DDS

- **Depends on:** P.2 merged; F3 (Foundation) `AuditSink`.
- **Deliverable:** a `phi` field crossing the DDS transport triggers the
  same `AuditSink` call pattern Track A/E already establish for DB and
  event delivery — the transport changes, the audit obligation doesn't.
- **Tests:**
  - Integration: `phi` field over DDS emits exactly one `AuditSink`
    record per publish, matching Track A/E's pattern.
