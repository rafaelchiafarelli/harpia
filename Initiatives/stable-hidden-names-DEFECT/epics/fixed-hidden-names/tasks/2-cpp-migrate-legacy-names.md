## C++ migration renames legacy hash-suffixed hidden columns

- **Depends on:** task 1.
- **Contract:** the generated C++ `migrate_<name>` (SQLite + PG), before its
  add/drop column evolution, renames an introspected column matching
  `ID_<32 hex>` → `HARPIA_ID`, `STATUS_<32 hex>` → `HARPIA_STATUS`,
  `ERROR_<32 hex>` → `HARPIA_ERROR`, `ORIGINATOR` or `ORIGINATOR_<32 hex>` →
  `HARPIA_ORIGINATOR`, when the target column is absent. Idempotent: a second
  run is a no-op. Rows and key values survive.
- **1. Corroborate (red first):** `test_stage8_db.py::test_migrate_renames_legacy_hidden_columns`
  — create a SQLite table with the legacy columns + one row, run the generated
  migration, `read` the row by its key. Fails today (drop of the PK column).
- **2. Fix:** `Database/MigrationAdapter.py` (+ `Database/backends/*` if the
  rename SQL needs a helper) — same place `renamed_from` renames run.
- **3. Unit tests (kept):** the red test + a PG twin in `test_stage8_pg.py`.
- **Golden move:** `UnitTests/golden/migrate/`.
- **Docs:** `Database/CLAUDE.md`; `USAGE.md` §10 (root-file changes no longer
  touch existing databases; legacy names are renamed once).
