## phi columns get the TEXT type in the shared DDL

- **Depends on:** nothing.
- **Planning default (2026-10-05):** `NOT NULL` on a `required` phi column
  stays — the ciphertext is never NULL. Flagged to Rafael with the plan;
  revisit only if he objects.
- **1. Corroborate (red first):**
  - The pinned strict xfails already encode the defect:
    `test_python_db_postgres.py` (`_PHI_NUMERIC_ON_PG`, `patient_vitals`) and
    `test_db_xlang3.py::test_pg_phi_numeric_column`. Run them on unmodified
    code and confirm they **xfail** with `InvalidTextRepresentation` (not some
    other error).
  - Add `UnitTests/test_stage8_pg.py::test_pg_phi_numeric_roundtrip` — the
    C++ DAO `create` + `read` of a `patient_vitals` row on live PG. Must
    **fail** on unmodified code (`create` returns false). If any of these
    passes, record the finding and stop.
  - Add `UnitTests/test_stage8_db.py::test_phi_columns_are_text_in_ddl` —
    parse the generated `database/*.sql` for both dialects and assert every
    phi column is TEXT. Fails today (`REAL` / `DOUBLE PRECISION`).
- **2. Fix:** `Database/model.py`: a column whose field `is_phi` takes
  `backend.sql_type("string")` instead of its scalar type (both dialects, via
  the `DbBackend`, no dialect `if`). Its bind *kind* stays text, so the
  C++/Python/Java DAOs need no change beyond regeneration.
- **3. Unit tests (required, kept):**
  - `test_pg_phi_numeric_roundtrip` and `test_phi_columns_are_text_in_ddl`
    (above) — now green.
  - Remove the strict-xfail marks in `test_python_db_postgres.py` and
    `test_db_xlang3.py`; those tests now pass as ordinary tests.
- **Golden move:** `UnitTests/golden/`, `UnitTests/golden_python/` (and
  `golden_java/` if affected); review that only phi column types changed.
