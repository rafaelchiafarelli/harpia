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

## Decisions (Rafael, 2026-11-01)

- **read-by-unique scope:** every top-level scalar `unique` field that is not
  `phi` (a phi value is encrypted with a random nonce — SQL can't match it;
  documented as unsupported). Embedded flat `unique` fields: not now.
- **db-assigned-key:** see `db-assigned-key/tasks/1-dsl-modifier-decision-done.md`
  — an `autokey` message modifier; `create()` with `HARPIA_ID` already set
  is an error; the assigned key is written back.

## Definition of done

- Each epic: its contract delivered in C++, Python and Java, SQLite + PG,
  goldens reviewed, `USAGE.md` §7 / §16 updated.
- Full Docker suite + `Docker/run_pg_tests.sh` green before merging to `dev`.
