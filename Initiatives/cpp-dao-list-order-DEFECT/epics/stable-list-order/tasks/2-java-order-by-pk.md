## Java DAO list SELECT orders by the primary key

- **Depends on:** nothing in code; run after task 1 so goldens move one task
  at a time.
- **Finding (planning, 2026-10-05):** Java generates only `list(List<T>)`
  (`JavaDatabase/templates/*.tmpl` ~73, `"{select_all_sql}"` =
  `SELECT … FROM "<table>"`, `JavaCrudlAdapter.py:113`) — no paginated list,
  so no skip/duplicate risk, but the row order is still undefined on PG and
  differs from C++/Python after task 1. Fix it for cross-language parity.
- **1. Corroborate (red first):** add
  `UnitTests/test_java_db_crudl_postgres.py::test_java_pg_list_in_pk_order`
  — insert rows, UPDATE some, `list()` → assert ascending pk order. Must
  **fail** on unmodified code. If it passes, record the finding and stop.
- **2. Fix:** a separate `select_list_sql = select_all_sql + ' ORDER BY
  "<pk>"'` used by `list()` only (`select_by_pk_sql` is built from
  `select_all_sql` and must not get an ORDER BY).
- **3. Unit tests (required, kept):**
  - `test_java_pg_list_in_pk_order` (above) — now green.
  - `test_java_db_crudl.py::test_java_sqlite_list_in_pk_order` — SQLite
    regression.
- **Golden move:** `UnitTests/golden_java/`; diff is only the list SELECT.
