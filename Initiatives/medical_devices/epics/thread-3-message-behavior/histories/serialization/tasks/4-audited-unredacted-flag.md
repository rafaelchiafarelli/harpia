## Session F.4 — Audited unredacted-output flag

- **Depends on:** F.3 merged; F3 (Foundation) `AuditSink`.
- **Deliverable:** unredacted output only emitted when an explicit,
  non-default flag is set (e.g. `--allow-phi-print`); any use of that
  flag is itself an audited event, not a silent one.
- **Tests:**
  - Unit: unredacted flag reveals the real value AND emits an audit
    record.
