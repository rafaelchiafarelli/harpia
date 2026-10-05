## JdbcBind.extract leaves a NULL column at the field default

- **Depends on:** nothing.
- **Deliverable:** `JdbcBind.extract` checks `rs.wasNull()` (or `getObject ==
  null`) for every kind and, on NULL, clears the field (`builder.clearField`)
  — the C++/Python behavior (default value; for an `optional` field, absent).
  Applies to INT/LONG/FLOAT/DOUBLE/ENUM too (today `getInt` silently gives 0
  for NULL, which is right for proto3 scalars but wrong for presence-tracked
  `optional` ones — check against C++).
- **Golden move:** `UnitTests/golden_java/` (runtime copy).
- **Tests:** `test_java_db_crudl.py` gains a NULL-row read (row inserted by raw
  SQL with NULL text and numeric columns); remove the strict xfails in
  `test_db_xlang3.py`.
