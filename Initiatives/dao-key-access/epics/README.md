# dao-key-access — epics

```
read-by-unique                      db-assigned-key
  1-cpp-read-by-unique                1-dsl-modifier-decision   (Rafael)
          │                                   │
          ├──────────────┐                    ▼
          ▼              ▼            2-cpp-db-assigned-key
  2-python-...     3-java-...                 │
                                       ┌──────┴──────┐
                                       ▼             ▼
                               3-python-...    4-java-...
```

The two epics don't depend on each other.

## Decisions for Rafael (planning, before code)

- **read-by-unique + phi:** a `phi` `unique` field is stored encrypted with a
  random nonce, so it can't be matched in SQL. Recommended: no `read_by_` for
  phi fields (documented); alternative is a blind-index column (separate
  initiative).
- **read-by-unique scope:** top-level scalar `unique` fields only
  (recommended); embedded flat-column `unique` fields later if asked.
- **db-assigned-key:** see `db-assigned-key/tasks/1-dsl-modifier-decision.md`.

## Definition of done

- Each epic: its contract delivered in C++, Python and Java, SQLite + PG,
  goldens reviewed, `USAGE.md` §7 / §16 updated.
- Full Docker suite + `Docker/run_pg_tests.sh` green before merging to `dev`.
