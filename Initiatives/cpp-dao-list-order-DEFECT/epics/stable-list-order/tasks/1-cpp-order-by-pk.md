## C++ DAO list SELECTs order by the primary key

- **Depends on:** nothing.
- **Deliverable:** `Database/templates/crudl.h.tmpl` `list()` and
  `list(offset, limit)` emit `… FROM "{table}" ORDER BY "{id_col}"` (paginated:
  before `LIMIT/OFFSET`). Same column the Python DAO orders by
  (`PyDatabase/PyDatabaseAdapter.py` ~line 101) so C++ and Python agree.
- **Golden move:** regenerate `UnitTests/golden/` (`HARPIA_UPDATE_GOLDEN=1
  pytest UnitTests/test_golden.py`), review the diff is exactly the ORDER BY.
- **Tests:**
  - PostgreSQL (opt-in live-PG test): insert N rows, UPDATE some (to perturb
    heap order), page through with a small limit → every row exactly once, in
    pk order.
  - SQLite: same assertion (regression).
- **Docs:** `Database/CLAUDE.md` list semantics; drop the "C++ has no ORDER BY"
  caveat in `PyDatabase/CLAUDE.md` if python-target is on the branch.
