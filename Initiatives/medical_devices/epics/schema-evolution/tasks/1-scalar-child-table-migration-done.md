## Repeated-scalar child-table migration

- **Depends on:** none (see Receives above).
- **Deliverable:** wire `MigrationAdapter._render()` to also call
  `repeated_fields()` (today it only calls `analyze()`); implement
  rename/add/drop/retype for repeated-scalar child tables.
- **Guarantees:** `migrate_<table>()` correctly handles repeated-scalar
  child-table schema changes without data loss outside what the
  transform itself specifies.
- **Tests:**
  - Unit: repeated-scalar child table migrated in isolation, each
    transform type (rename/add/drop/retype).
  - Integration: old DB snapshot + new schema version with a
    repeated-scalar field → migrate → verify data integrity.
