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
