# cpp-phi-numeric-column-type-DEFECT — epics

One epic: **`phi-column-type`**.

```
1-phi-columns-are-text
        │
        ▼
2-migrate-existing-phi-columns
```

## Definition of done

- Every `phi` column is TEXT in the DDL of both dialects; golden diffs show
  only those type changes.
- The two strict xfails named in `../README.md` now pass (remove the marks).
- Live-PG tests (`Docker/run_pg_tests.sh`) and the full Docker suite green
  before merging up to `dev`.
