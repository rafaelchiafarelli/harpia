## Python DAO mirrors task 1

- **Depends on:** task 1.
- **Contract:** `<Msg>_dao.read_by_<f>(value, out) -> bool`, same semantics
  as task 1 (`PyDatabase/runtime/dao.py` + adapter metadata).
- **Tests (kept):** `test_py_db_dao.py::test_read_by_unique` (SQLite + PG).
- **Golden move:** `UnitTests/golden_python/`.
- **Docs:** `PyDatabase/CLAUDE.md`, `USAGE.md` §7.
