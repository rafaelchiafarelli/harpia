# Numeric `phi` columns keep a numeric SQL type — unusable on PostgreSQL — DEFECT

**Status: scoped, not started.** Found 2026-10-04 (python-target
`py-crypto-phi/4`; decisions log item 26 in
`Initiatives/python-target/NEXT_SESSION.md`). Not fixed: it moves `golden/`.

## What was found

A `phi` field is stored encrypted: the DAO writes `enc:v1:<hex>` **text** into
its column. But the shared DDL (`Database/model.py` → `Column.sql_def()`, the
type comes from `backend.sql_type(token)` with no regard to `is_phi`) keeps the
field's numeric type:

- `patient_vitals.heart_rate` (`phi required float`) → `REAL NOT NULL`
  (SQLite) / `DOUBLE PRECISION NOT NULL` (PostgreSQL).

SQLite accepts the text anyway (type affinity), so every SQLite test passes.
**PostgreSQL rejects it** (`InvalidTextRepresentation`): the C++ DAO's
`create` returns false, the Python DAO raises. Any numeric/enum `phi` column is
unusable on PostgreSQL in every language.

Pinned as strict xfails, which will flip when this is fixed:
`test_python_db_postgres.py` (`patient_vitals`) and
`test_db_xlang3.py::test_pg_phi_numeric_column`.

## Scope

One epic: **`phi-column-type`**. Changes DDL → **moves `UnitTests/golden/`**
(sidecar `database/*.sql`, crudl headers, migrate specs) and `golden_python/`;
check `golden_java/` (Java has no phi support, but shares the DDL source). An
existing database needs a migration step (numeric → TEXT retype). See
`epics/README.md`.
