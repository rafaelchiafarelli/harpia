## C++ DAO list SELECTs order by the primary key

- **Depends on:** nothing.
- **1. Corroborate (red first):** add
  `UnitTests/test_stage8_pg.py::test_pg_list_pages_are_stable` (opt-in live
  PG, `Docker/run_pg_tests.sh`): insert N≈50 rows via the generated C++ DAO,
  UPDATE every other row (moves those tuples to the heap's end), then page
  through `list(offset, limit)` with limit 7 and also call `list()`. Assert
  every pk appears exactly once **and** in ascending pk order. On unmodified
  code it must **fail** (no `ORDER BY` in `crudl.h.tmpl` ~73/~87, so PG
  returns heap order — at minimum the order assertion trips). If it passes
  even after the UPDATE perturbation, add a `VACUUM` and re-run; if it still
  passes, record the finding and stop.
- **2. Fix:** `Database/templates/crudl.h.tmpl` `list()` and
  `list(offset, limit)` emit `… FROM "{table}" ORDER BY "{id_col}"`
  (paginated: before `LIMIT/OFFSET`) — the same column the Python DAO orders
  by (`PyDatabase/PyDatabaseAdapter.py` ~148) so C++ and Python agree.
- **3. Unit tests (required, kept):**
  - `test_pg_list_pages_are_stable` (above) — now green.
  - `UnitTests/test_stage8_db.py::test_sqlite_list_pages_are_stable` — the
    same assertion on SQLite (regression; passes before and after).
  - A golden assertion is implicit: the regenerated crudl headers carry the
    `ORDER BY`.
- **Golden move:** `HARPIA_UPDATE_GOLDEN=1 pytest UnitTests/test_golden.py`;
  the diff is exactly the ` ORDER BY "<id_col>"` in the list SELECTs.
- **Docs:** `Database/CLAUDE.md` list semantics; drop the "the C++ DAO has no
  ORDER BY" comment at `PyDatabase/PyDatabaseAdapter.py` ~146 and any
  matching caveat in `PyDatabase/CLAUDE.md`.
