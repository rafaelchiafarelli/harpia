# java-jdbc-null-text-DEFECT — epics

One epic: **`jdbc-null-handling`**.

```
1-null-reads-as-default
        │
        ▼
2-deferred-header-lists-child-tables
```

## Definition of done

- `test_db_xlang3.py`'s Java pre-migration xfails pass (marks removed).
- `golden_java/` diffs reviewed: only these changes.
- Full Docker suite (and `Docker/run_pg_tests.sh`) green before merging up to
  `dev`.
