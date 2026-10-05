# cpp-pg-introspection-schema-DEFECT — epics

One epic: **`schema-qualified-introspection`** — one task,
`1-filter-current-schema`. The fix lives in the shared backend, so C++ and
(when present on the branch) Python pick it up together.

## Definition of done

- Golden diff reviewed: only the three PG introspection queries change; SQLite
  untouched.
- Live-PG tests (`Docker/run_pg_tests.sh`) pass, including the new
  two-schema test.
- Full Docker suite green before merging up to `dev`.

## Decision for Rafael (planning, before implementing)

Which schema to filter on: `current_schema()` (search_path's first entry —
matches where unqualified `CREATE TABLE` lands, the conservative default) vs.
an explicit, configurable schema (new `.harpia`/connection contract — bigger,
needs its own task). The task below assumes `current_schema()`.
