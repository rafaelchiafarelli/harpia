## Schema migration — main table (ensure, rename, add, `data_transform`, drop, retype)

- **Depends on:** task 2c (needs the full current column set).
- **Contract:** `harpia_generated/migrate/<name>_<hash>_migrate.py`, with
  `migrate_<name>(conn, data_transform=None)` porting `MigrationAdapter`'s
  main-table logic **in the same order**:
  1. ensure the table exists;
  2. RENAME `renamed_from[<old>]` columns, correcting the introspected set;
  3. ADD missing non-PK columns;
  4. call `data_transform(conn)`;
  5. DROP undeclared columns;
  6. RETYPE mismatched columns: Postgres via `ALTER COLUMN … TYPE`, SQLite
     via the rebuild-and-copy path from `DbBackend.retype_column_dynamic`;
  7. record the version in `_harpia_schema_version`.

  Reuse the `DbBackend` dynamic-SQL methods C++ uses. Don't re-derive
  dialect SQL in the Python adapter.
- **Watch for:** the ADD-before-transform / transform-before-DROP order is
  load-bearing: the split-column case breaks if reversed (`Database/CLAUDE.md`).
- **Bar:** a database migrated by Python ends in the same schema +
  `_harpia_schema_version` row as one migrated by C++ from the same
  starting state.
- **Out of scope:** child tables (5b).
- **Tests:**
  - v1 → v2 schema-evolution tests on SQLite (rename keeps data, add, drop,
    retype, `data_transform` split-column case).
  - A g++-gated case where C++ creates v1 and Python migrates it to v2.
  - Postgres variants opt-in (`HARPIA_PG_DSN`).
