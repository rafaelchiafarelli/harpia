## C++ DAO: unset optional binds NULL, NULL reads back absent

- **Depends on:** the decisions in `../../README.md`.
- **1. Corroborate (red first):** `test_stage8_db.py::test_optional_presence_round_trip`
  — `patient_vitals` with `device_note` unset, and another row with it set to
  `""`; `create` + `read`: the unset one must come back `!has_device_note()`
  and the column must be NULL; the set one present. Fails today (present,
  `""` stored).
- **2. Fix:** `Database/CrudlAdapter.py` — for a column whose field has
  explicit presence: bind with a `::soci::indicator` (`i_null` when
  `!has_x()`), and on extract leave the field unset when the indicator is
  `i_null`. Proto3 implicit scalars unchanged.
- **3. Unit tests (kept):** the red test (SQLite) + a PG twin in
  `test_stage8_pg.py`.
- **Golden move:** `UnitTests/golden/db/` for messages with `optional`
  fields only.
