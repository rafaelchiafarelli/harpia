## Python DAO mirrors task 1

- **Depends on:** task 1.
- **1. Corroborate (red first):** `test_py_db_bind.py::test_unset_optional_is_null_and_absent`
  — bind of an unset `optional` is `None`; extract of `None` into an
  `optional` leaves `HasField` false. Fails today.
- **2. Fix:** `PyDatabase/runtime/bind.py` (`bind_value` / `extract_value`
  presence-aware); same rule as C++.
- **3. Unit tests (kept):** the red test; `test_py_db_dao.py` round trip of
  `patient_vitals` with `device_note` unset; golden_python runtime copy
  regenerated.
