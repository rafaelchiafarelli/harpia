
## `AuditSink` wiring on `phi` CRUDL ops + `ComplianceReport` note

- **Depends on:** task 1, task 2 merged; F3's `AuditSink`.
- **Deliverable:** `AuditSink.record()` call at each DAO CRUDL operation
  touching a `phi` field; one-paragraph note added to `ComplianceReport/`
  describing what changed and why (feeds the process-artifacts epic later).
- **Tests:**
  - Unit: mock `AuditSink`, assert exactly one call per DAO op with
    correct field-level detail.