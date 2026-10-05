## PG introspection queries filter `table_schema = current_schema()`

- **Depends on:** nothing (shared `Database/backends/postgres.py`).
- **Deliverable:** `list_columns_sql`, `list_column_types_sql` and
  `list_tables_sql` in `Database/backends/postgres.py` add
  `AND table_schema = current_schema()`. Nothing else changes; SQLite backend
  untouched.
- **Golden move:** regenerate `UnitTests/golden/`, review that only these
  queries changed (and `golden_python/` too if python-target is on the
  branch).
- **Tests (live PG):** create a decoy schema with a same-named table carrying
  extra / differently-typed columns and a `<table>__x` child table; run the
  C++ migrate binary → the decoy's columns and child tables are neither added,
  dropped, retyped nor reaped; end state equals the single-schema run.
  If python-target is on the branch, run the same on the Python engine and
  remove the throwaway-DATABASE workaround from
  `test_python_db_postgres.py::test_migrate_on_postgres`.
- **Docs:** `Database/CLAUDE.md` (migration introspection scope).
