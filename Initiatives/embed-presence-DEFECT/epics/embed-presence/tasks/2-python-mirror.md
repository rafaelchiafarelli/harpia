## Python DAO mirrors task 1

- **Depends on:** task 1.
- **Contract:** the Python DAO (`PyDatabase/runtime/dao.py` +
  `PyDatabaseAdapter`) binds/reads the `HARPIA_HAS_<prefix>` columns with the
  C++ rule (absent embed → 0 + NULL sub-columns; 0 → embed left unset, no
  `SetInParent()`; NULL → present). The Python migration adds the column.
- **1. Corroborate (red first):**
  `test_py_db_dao.py::test_embed_presence_round_trip` (same cases as task 1).
- **3. Unit tests (kept):** the red test; golden_python moved.
