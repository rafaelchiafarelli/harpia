## `AuditSink` hook on `OnChange` + full round-trip

- **Depends on:** task 1, task 2 merged; F3's `AuditSink`.
- **Deliverable:** `AuditSink` hook fires on `OnChange`, specifically for
  `phi` fields; one-paragraph `ComplianceReport/` note (feeds the process-artifacts epic
  later).
- **Tests:**
  - Integration: subscribe → mutate → assert the callback fires with the
    correct payload, and for `phi` fields an audit record is emitted.
- **Acceptance gate:** new functionality, no prior behavior to preserve —
  100% pass on this epic's own new tests.
---
## Epic context — events-callbacks

**Contract.** `event[cached/not-cached]` implementation, detached-thread callback
dispatch with exception isolation, and an `AuditSink` hook on `OnChange` for `phi`
fields. Needs `ComplianceContext` and the `AuditSink` stub from Foundation. No
epic technically depends on this; the serialization redaction-hook design is
described as benefiting from seeing this audit-hook pattern first (precedent, not
a dependency).

**Files.** `Logger/`, new `Callback/` module.
