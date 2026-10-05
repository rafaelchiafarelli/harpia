# PostgreSQL migration introspection is not schema-qualified — DEFECT

**Status: scoped, not started.** Found 2026-10-04 while porting schema
migration to Python (python-target `py-database/5a`; decisions log item 19 in
`Initiatives/python-target/NEXT_SESSION.md`). The C++ code was not changed;
the Python migration shares the same SQL (both come from
`Database/backends/postgres.py`), so it has the same bug. The Python PG
migration test works around it with a throwaway DATABASE.

## What was found

`Database/backends/postgres.py` (emitted into the C++ migrate code via
`Database/MigrationAdapter.py` ~lines 165-173, and used by the Python engine):

- `list_columns_sql` (~line 114): `SELECT column_name FROM
  information_schema.columns WHERE table_name = '<t>'`
- `list_column_types_sql` (~line 138): same, plus `data_type`
- `list_tables_sql` (~line 141): `SELECT table_name FROM
  information_schema.tables WHERE substr(table_name, …) = '<prefix>__'`

None filter on `table_schema`. If the same table name exists in another
schema of the database (another app, a `test` schema, a second Harpia
deployment in the same DB), its columns / child tables leak into the
migration diff → spurious ADD/DROP/RENAME/retype, child-table reaps of tables
the migration doesn't own. That is a **data-loss** risk on shared databases.

## Scope

One epic: **`schema-qualified-introspection`**. Changes generated SQL →
**moves `UnitTests/golden/` bytes** (PostgreSQL dialect only); intended.
See `epics/README.md`.
