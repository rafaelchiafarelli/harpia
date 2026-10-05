## Existing databases: generated migration retypes phi columns to TEXT

- **Depends on:** task 1.
- **1. Corroborate (red first):** add
  `UnitTests/test_stage8_db.py::test_migrate_retypes_legacy_phi_column` (and
  the PG twin in `test_stage8_pg.py`): hand-build an "older"
  `patient_vitals_table` with `heart_rate REAL` holding ciphertext rows
  written by the pre-fix DAO (SQLite accepts it), run the C++ migrate binary,
  assert the column is TEXT and every row still decrypts to its original
  value. Same for the Python engine in
  `test_python_db_postgres.py` / the Python SQLite migrate test. The
  expectation is that the existing retype-on-mismatch path already fires —
  so this test may pass immediately; that is a valid outcome and is
  recorded as "migration path verified, no code change".
- **2. Fix (only if 1 fails):** make the retype fire for numeric → TEXT;
  verify the CAST of existing values preserves the `enc:v1:` text exactly.
  (Plaintext numeric rows can't exist on PG — the DAO always wrote
  ciphertext and PG rejected it; on SQLite they are ciphertext too.)
- **3. Unit tests (required, kept):** `test_migrate_retypes_legacy_phi_column`
  (C++ SQLite + PG, Python SQLite + PG).
- **Docs:** `Database/CLAUDE.md` — phi columns are TEXT; legacy numeric phi
  columns are retyped by the generated migration.
