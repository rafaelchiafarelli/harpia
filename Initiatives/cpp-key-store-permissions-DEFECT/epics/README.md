# cpp-key-store-permissions-DEFECT — epics

One epic: **`key-store-permissions`**.

```
1-cpp-store-0600
        │
        ▼
2-python-store-0600   (mirrors task 1; ordered so the two languages agree)
```

## Definition of done

- A KEK store and its `.shred` sidecar created by either language are `0600`
  regardless of umask; an existing store with looser bits is either tightened
  or refused (task 1 decides, task 2 follows — flag the choice to Rafael).
- C++ ↔ Python store interop tests (`test_py_key_provider_backends.py`) still
  pass.
- Full Docker suite green before merging up to `dev`.
