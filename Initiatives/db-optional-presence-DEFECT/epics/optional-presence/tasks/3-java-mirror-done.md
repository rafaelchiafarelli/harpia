## Java DAO mirrors task 1

- **Depends on:** task 1.
- **1. Corroborate (red first):** `test_java_db_crudl.py::test_java_optional_presence`
  — the `nullable_row` fixture's `optional` fields: unset → NULL stored,
  read back `!hasField`; set to 0 → present. Fails today.
- **2. Fix:** `JavaDatabase/runtime/JdbcBind.java` — `bind` uses
  `ps.setNull(index, sqlType)` when `fd.hasPresence() && !msg.hasField(fd)`;
  `extract` leaves a presence field cleared on NULL (other fields keep the
  default, as since java-jdbc-null-text-DEFECT).
- **3. Unit tests (kept):** the red test; golden_java runtime copy
  regenerated.
- **Embedded fields (decision 2026-10-31):** the same rule for the `optional`
  fields of an embedded sub-message stored as flat columns; the red test adds
  a row whose embedded optional is unset (NULL column, absent after read) and
  one where it is set to its default (present). An unset phi `optional` binds
  NULL without encrypting.
