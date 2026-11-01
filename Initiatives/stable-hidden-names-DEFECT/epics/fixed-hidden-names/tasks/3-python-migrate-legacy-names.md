## Python migration renames legacy hash-suffixed hidden columns

- **Depends on:** task 1 (and mirrors task 2's contract exactly).
- **Contract:** as task 2, for the generated Python `migrate_<name>(conn)`
  (`PyDatabase/runtime/migrate.py` + adapter), SQLite + PG.
- **1. Corroborate (red first):** `test_py_db_migrate.py::test_migrate_renames_legacy_hidden_columns`
  — the `harpia-handoff.md` reproduction: a table + row with `ID_<hash>` /
  `STATUS_<hash>` / `ERROR_<hash>` / `ORIGINATOR`, the new migration, the row
  read back through the DAO with its key. Fails today.
- **2. Fix:** `PyDatabase/runtime/migrate.py` (rename step, before step 4's
  `renamed_from` renames correct the introspected set).
- **3. Unit tests (kept):** the red test + its PG twin.
- **Golden move:** `UnitTests/golden_python/` runtime copy.
- **Docs:** `PyDatabase/CLAUDE.md`.
