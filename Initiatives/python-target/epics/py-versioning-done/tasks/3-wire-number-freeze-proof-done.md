## Proof: wire-number freezing holds for Python peers across schema versions

- **Depends on:** `py-foundation` task 2; `py-zmq` task 1.
- **Contract:** no new runtime. `Message/FieldMap` already freezes field
  numbers into the `.proto` that every target compiles. This task proves
  the property end-to-end for Python, since nothing has exercised it yet.
  - From schema v1, generate Python v1. Evolve the schema to v2 (add a
    field, rename one via `renamed_from`, remove one) reusing the same
    `schema_registry/`, and generate Python v2.
  - v1 bytes parse in v2: renamed fields keep their values, and removed
    numbers are `reserved` and never reused. v2 bytes parse in v1:
    unknown fields are tolerated, and JSON/XML parse ignores unknown keys.
  - Cross-target: C++ v1 → Python v2 over ZMQ.
- **Out of scope:** any change to `FieldMap`. If the proof finds a
  violation, that is a **stop-and-flag** (a front-end bug affecting every
  target), not a Python-side workaround.
- **Tests:** the scenario above as `UnitTests/test_python_versioning.py`
  (temp copies of the fixture; never touch the committed
  `schema_registry/`, which is git-ignored and per-checkout).
