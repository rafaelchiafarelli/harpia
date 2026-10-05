## Python YAML reader mirrors the fix; parity fixture uses negative keys

- **Depends on:** task 1. python-target's `PySerialization/runtime/yaml.py`
  is on `dev` (shipped 2026-10-05).
- **1. Corroborate (red first):** add
  `UnitTests/test_py_yaml.py::test_py_yaml_map_negative_int_keys` — the
  Python mirror of task 1's round trip (same fixture). Must **fail** on the
  unmodified Python runtime (`yaml.py` ~229/266/311 decide item-vs-key on
  `startswith("-")`). If it passes, stop and record the finding.
- **2. Fix:** the same item-vs-key rule in `PySerialization/runtime/yaml.py`
  (one helper, every call site); drop the "non-negative map keys only"
  restriction from `UnitTests/_py_cpp_parity.py` and the note in
  `PySerialization/CLAUDE.md` (~line 72).
- **3. Unit tests (required, kept):**
  - `test_py_yaml_map_negative_int_keys` (above) — now green.
  - Parity: the negative keys in `_py_cpp_parity.py` make
    `test_serialize_xlang3.py::test_yaml_cpp_equals_python` assert
    byte-identical `to_yaml` and equal messages C++ ↔ Python both directions.
- **Golden:** regenerate `UnitTests/golden_python/` only if the runtime is
  snapshotted there; diff must be only this change.
- **Quality gate:** `test_python_quality_gate.py` (ruff + mypy).
