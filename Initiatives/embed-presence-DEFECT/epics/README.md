# embed-presence-DEFECT — epics

```
1-cpp-embed-presence-column
        │
        ▼
2-python-mirror
        │
        ▼
3-cross-language-embed-presence
```

## Definition of done

- C++ and Python: an unset embedded message field round-trips as unset
  (`HARPIA_HAS_<path>` = 0), a set one — even all-default — as set; nested
  levels independent; a NULL presence column (pre-change row) reads present.
- The C++ and Python migrations add the column to an existing table.
- Goldens reviewed; full Docker suite + `Docker/run_pg_tests.sh` green before
  merging to `dev`.
