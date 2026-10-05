# cpp-dao-list-order-DEFECT — epics

One epic: **`stable-list-order`**.

```
1-cpp-order-by-pk
        │
        ▼
2-java-order-by-pk   (independent of 1 in code; ordered only to keep one golden move per task)
```

## Definition of done

- Golden diffs reviewed: the ONLY change is ` ORDER BY "<id_col>"` added to the
  list SELECTs (both SQLite and PostgreSQL dialects).
- Live-PG tests (`Docker/run_pg_tests.sh`) pass.
- Full Docker suite green before merging up to `dev`.
