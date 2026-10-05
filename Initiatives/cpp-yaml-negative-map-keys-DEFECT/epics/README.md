# cpp-yaml-negative-map-keys-DEFECT — epics

One epic: **`yaml-negative-keys`**.

```
1-cpp-dash-is-item-only-with-space
        │
        ▼ (needs python-target's PySerialization on the same branch)
2-python-mirror
```

## Definition of done

- Task tests + `test_golden*.py` pass. Preferred fix is reader-only, so goldens
  should NOT move; if the chosen fix changes `to_yaml` bytes instead (e.g.
  quoting negative keys), that is a contract change — stop and ask Rafael
  first.
- Full Docker suite green before merging up to `dev`.
