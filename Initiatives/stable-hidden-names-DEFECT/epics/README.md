# stable-hidden-names-DEFECT — epics

One epic: **`fixed-hidden-names`**.

```
1-hash-free-hidden-names        (front end + every consumer + goldens)
        │
        ├──────────────────────────┐
        ▼                          ▼
2-cpp-migrate-legacy-names   3-python-migrate-legacy-names
```

Java has no migration (`JavaDatabase/CLAUDE.md`); task 1 covers its DAO.

## Definition of done

- Two generations from roots that differ in text produce the same hidden
  field/column names, in C++, Python and Java.
- A database made with `ID_<hash>` / `STATUS_<hash>` / `ERROR_<hash>` /
  `ORIGINATOR[_<hash>]` columns is migrated in place by the new
  `migrate_<name>` (C++ and Python, SQLite and PG) with its rows and key values
  intact — the `harpia-handoff.md` reproduction passes.
- `USAGE.md` §10 says what happens to existing databases when the root file
  changes; `harpia.process.md` stage 0 no longer says the hash qualifies
  hidden-field names.
- Full Docker suite + `Docker/run_pg_tests.sh` green before merging to `dev`.
