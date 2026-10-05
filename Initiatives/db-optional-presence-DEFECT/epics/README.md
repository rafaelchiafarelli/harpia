# db-optional-presence-DEFECT — epics

One epic: **`optional-presence`**.

```
1-cpp-null-for-unset-optional
        │
        ▼
2-python-mirror
        │
        ▼
3-java-mirror
        │
        ▼
4-cross-language-presence   (C++/Python/Java write ⇄ read on one database)
```

## Decisions for Rafael (planning, before code)

- **Scope of "optional":** only fields with explicit presence (`optional`
  scalars); proto3 implicit scalars keep reading NULL as default (no change).
- **Existing rows:** rows written before the fix hold `0`/`""` for an unset
  `optional`, indistinguishable from an explicit value — they keep reading
  as present. Document it; no data migration (recommended), or offer an
  opt-in migration hook?
- **`optional` + phi:** an unset phi `optional` stores NULL (no ciphertext)
  — recommended; the alternative (encrypting a marker) leaks nothing but
  costs a DEK per absent value.

## Definition of done

- In every language: unset `optional` → NULL column; NULL column → field
  absent (`has_x() == false`); set-to-0 → `0` stored → present after read.
- `test_py_db_bind.py`'s presence assertion extended to the read half.
- Goldens reviewed (C++ DAO bind/extract lines, Python runtime copy, Java
  runtime copy).
- Full Docker suite + `Docker/run_pg_tests.sh` green before merging to `dev`.
