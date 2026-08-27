
## Session E.2 — Detached-thread callback dispatch + exception isolation

- **Depends on:** E.1 merged.
- **Deliverable:** callback dispatch runs on a detached thread; a
  try-catch boundary ensures a callback's own exception never propagates
  to the caller thread.
- **Tests:**
  - Unit: callback exception isolation — an exception thrown inside a
    callback doesn't crash or propagate to the caller.