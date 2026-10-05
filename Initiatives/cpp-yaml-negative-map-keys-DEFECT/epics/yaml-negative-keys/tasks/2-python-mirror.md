## Python YAML reader mirrors the fix; parity fixture uses negative keys

- **Depends on:** task 1, and python-target's `py-serialization` epic present
  on the branch (`PySerialization/runtime/yaml.py`).
- **Deliverable:** the same item-vs-key rule in
  `PySerialization/runtime/yaml.py`; drop the "non-negative map keys only"
  restriction from the YAML parity fixture in `UnitTests/_py_cpp_parity.py`
  (and the note in `PySerialization/CLAUDE.md`).
- **Tests:** parity test with negative map keys — C++ ↔ Python both
  directions, byte-identical `to_yaml`, equal messages after `from_yaml`.
- **Quality gate:** `test_python_quality_gate.py` (ruff + mypy on the
  generated tree).
