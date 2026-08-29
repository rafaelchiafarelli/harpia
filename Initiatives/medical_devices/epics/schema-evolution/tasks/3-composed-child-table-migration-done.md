## Repeated-composed child-table migration

- **Depends on:** task 1 merged (`repeated_fields()` wiring already in
  place, reused here — task 2 not required first, task 2 and task 3 could swap
  order).
- **Deliverable:** implement rename/add/drop/retype for
  repeated-composed child tables.
- **Guarantees:** same as task 1, for repeated-composed child tables.
- **Tests:** same shape as task 1, for repeated-composed fields.
- **Acceptance gate (covers task 1–task 3 together):** existing
  additive-migration and `data_transform`-hook tests unchanged.