## Session E.1 — `event[cached/not-cached]` implementation

- **Depends on:** F1 (Foundation).
- **Deliverable:** `event[cached/not-cached]` firing on create/change/
  update; cached subscriptions receive the last value immediately on
  subscribe; `read` never fires an event.
- **Tests:**
  - Unit: cached vs. not-cached delivery semantics.