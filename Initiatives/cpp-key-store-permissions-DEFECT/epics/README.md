# cpp-key-store-permissions-DEFECT — epics

One epic: **`key-store-permissions`**.

```
1-cpp-store-0600
        │
        ▼
2-python-store-0600   (mirrors task 1; ordered so the two languages agree)
```

## Decision (Rafael, 2026-10-05)

An existing KEK store or `.shred` sidecar with any group/other permission bit
set is **refused** (fail-safe: the KEK may already have leaked, the operator
must act — `chmod 0600` after rotating if exposure is possible). It is never
silently tightened.

## Definition of done

- A KEK store and its `.shred` sidecar created by either language are `0600`
  regardless of umask; a loose existing one is refused by both languages.
- C++ ↔ Python store interop tests (`test_py_key_provider_backends.py`) still
  pass.
- Full Docker suite green before merging up to `dev`.
