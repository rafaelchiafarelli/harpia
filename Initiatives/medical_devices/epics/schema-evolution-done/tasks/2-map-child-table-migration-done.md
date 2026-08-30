## Map child-table migration

- **Depends on:** task 1 merged (reuses its `_render()` wiring pattern —
  do task 1 first even though the two don't share code paths).
- **Deliverable:** wire `MigrationAdapter._render()` to also call
  `map_fields()`; implement rename/add/drop/retype for map child tables.
- **Guarantees:** same as task 1, for map child tables.
- **Tests:** same shape as task 1 (unit per transform type, integration
  round trip), for map fields.