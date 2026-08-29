## `event[cached/not-cached]` implementation

- **Depends on:** F1 (Foundation).
- **Deliverable:** `event[cached/not-cached]` firing on create/change/
  update; cached subscriptions receive the last value immediately on
  subscribe; `read` never fires an event.
- **Tests:**
  - Unit: cached vs. not-cached delivery semantics.
---
## Epic context — events-callbacks

**Contract.** `event[cached/not-cached]` implementation, detached-thread callback
dispatch with exception isolation, and an `AuditSink` hook on `OnChange` for `phi`
fields. Needs `ComplianceContext` and the `AuditSink` stub from Foundation. No
epic technically depends on this; the serialization redaction-hook design is
described as benefiting from seeing this audit-hook pattern first (precedent, not
a dependency).

**Files.** `Logger/`, new `Callback/` module.
