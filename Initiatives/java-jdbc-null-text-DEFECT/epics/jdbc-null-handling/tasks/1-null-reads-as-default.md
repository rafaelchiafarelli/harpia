## JdbcBind.extract leaves a NULL column at the field default

- **Depends on:** nothing.
- **1. Corroborate (red first):**
  - The pinned strict xfails already encode it:
    `test_db_xlang3.py` `_JAVA_NULL_TEXT` (`test_*_java_reads_pre_migration_row`,
    SQLite + PG). Run them on unmodified code and confirm they xfail with the
    `NullPointerException` from `setField` (`JdbcBind.java` ~75).
  - Add `UnitTests/test_java_db_crudl.py::test_java_reads_null_columns` — a
    row inserted by raw SQL with NULL in a text, an int, a double and an enum
    column (and, if the fixture has one, a proto3 `optional` scalar); Java
    `read` and `list` it. Must **fail** today (NPE on the text column).
    If it passes, record the finding and stop.
  - In the same test, capture what C++ does for the `optional` NULL column
    (expected: field absent). That is the reference behavior.
- **2. Fix:** `JavaDatabase/runtime/JdbcBind.java` `extract` reads the value,
  checks `rs.wasNull()` for every kind, and on NULL calls
  `builder.clearField(fd)` (default value; `optional` → absent), matching
  C++/Python.
- **3. Unit tests (required, kept):**
  - `test_java_reads_null_columns` (above) — now green; asserts text = `""`,
    numerics = 0, enum = first value, `optional` = absent.
  - Remove the strict-xfail marks in `test_db_xlang3.py`; those tests now
    pass as ordinary tests.
  - Existing `test_bind_extract_roundtrip_per_supported_type` stays green.
- **Golden move:** `UnitTests/golden_java/` (runtime copy).
