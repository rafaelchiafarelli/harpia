## phi columns get the TEXT type in the shared DDL

- **Depends on:** nothing.
- **Decision needed (planning):** `NOT NULL` on a `required` phi column stays
  (the ciphertext is never NULL) — confirm with Rafael.
- **Deliverable:** `Database/model.py`: a column whose field `is_phi` takes
  `backend.sql_type("string")` instead of its scalar type (both dialects, via
  the `DbBackend`, no dialect `if`). Its bind *kind* stays what the DAO binds
  today (text), so the C++/Python/Java DAOs need no change beyond
  regeneration.
- **Golden move:** `UnitTests/golden/`, `UnitTests/golden_python/` (and
  `golden_java/` if affected); review that only phi column types changed.
- **Tests:** remove the strict xfails in `test_python_db_postgres.py` and
  `test_db_xlang3.py`; `test_stage8_pg.py` gains a `patient_vitals` C++ round
  trip on PostgreSQL.
