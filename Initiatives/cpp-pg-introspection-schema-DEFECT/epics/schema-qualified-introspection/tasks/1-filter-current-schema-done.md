## PG introspection queries filter `table_schema = current_schema()`

- **Depends on:** nothing (shared `Database/backends/postgres.py`).
- **Decision (Rafael, 2026-10-05):** filter on `current_schema()`. A
  configurable schema is not in scope.
- **1. Corroborate (red first):** add
  `UnitTests/test_stage8_pg.py::test_pg_migration_ignores_other_schemas`
  (live PG): create schema `decoy` holding a same-named `<table>` with an
  extra column and a differently-typed column, plus a `decoy.<table>__x`
  child table. Run the generated C++ migrate binary against `public`. Assert
  `public.<table>`'s columns/types equal the single-schema run, nothing in
  `decoy` was dropped/altered, and no child table was reaped or created.
  Must **fail** on unmodified code (the three queries ~115/139/147 don't
  filter `table_schema`, so the decoy's columns enter the diff). If it
  passes, record the finding and stop.
- **2. Fix:** `list_columns_sql`, `list_column_types_sql` and
  `list_tables_sql` add `AND table_schema = current_schema()`. Nothing else;
  SQLite untouched.
- **3. Unit tests (required, kept):**
  - `test_pg_migration_ignores_other_schemas` (C++) — now green.
  - `UnitTests/test_python_db_postgres.py::test_py_migration_ignores_other_schemas`
    — same scenario on the Python engine (shares the backend SQL).
  - Remove the throwaway-DATABASE workaround from
    `test_python_db_postgres.py::test_migrate_on_postgres`; it must stay
    green without it.
- **Golden move:** `UnitTests/golden/` (+ `golden_python/` if the SQL is
  snapshotted there); only these three PG queries change.
- **Docs:** `Database/CLAUDE.md` (migration introspection scope =
  `current_schema()`).
