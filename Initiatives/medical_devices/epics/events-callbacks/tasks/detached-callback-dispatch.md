
## Detached-thread callback dispatch + exception isolation

- **Depends on:** task 1 merged.
- **Deliverable:** callback dispatch runs on a detached thread; a
  try-catch boundary ensures a callback's own exception never propagates
  to the caller thread.
- **Tests:**
  - Unit: callback exception isolation — an exception thrown inside a
    callback doesn't crash or propagate to the caller.
---
## Epic context — events-callbacks

**Contract.** `event[cached/not-cached]` implementation, detached-thread callback
dispatch with exception isolation, and an `AuditSink` hook on `OnChange` for `phi`
fields. Needs `ComplianceContext` and the `AuditSink` stub from Foundation. No
epic technically depends on this; the serialization redaction-hook design is
described as benefiting from seeing this audit-hook pattern first (precedent, not
a dependency).

**Files.** `Logger/`, new `Callback/` module.
