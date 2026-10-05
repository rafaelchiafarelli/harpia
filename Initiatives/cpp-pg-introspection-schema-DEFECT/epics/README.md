# cpp-pg-introspection-schema-DEFECT — epics

One epic: **`schema-qualified-introspection`** — one task,
`1-filter-current-schema`. The fix lives in the shared backend, so C++ and
Python pick it up together.

## Definition of done

- Golden diff reviewed: only the three PG introspection queries change; SQLite
  untouched.
- Live-PG tests (`Docker/run_pg_tests.sh`) pass, including the new
  two-schema tests (C++ and Python).
- Full Docker suite green before merging up to `dev`.

## Decision (Rafael, 2026-10-05)

Filter on `current_schema()` (search_path's first entry — where unqualified
`CREATE TABLE` lands). An explicit configurable schema would be a new
contract and is out of scope.
