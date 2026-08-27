## Session H.3 — Repeated-composed child-table migration

- **Depends on:** H.1 merged (`repeated_fields()` wiring already in
  place, reused here — H.2 not required first, H.2 and H.3 could swap
  order).
- **Deliverable:** implement rename/add/drop/retype for
  repeated-composed child tables.
- **Guarantees:** same as H.1, for repeated-composed child tables.
- **Tests:** same shape as H.1, for repeated-composed fields.
- **Acceptance gate (covers H.1–H.3 together):** existing
  additive-migration and `data_transform`-hook tests unchanged.