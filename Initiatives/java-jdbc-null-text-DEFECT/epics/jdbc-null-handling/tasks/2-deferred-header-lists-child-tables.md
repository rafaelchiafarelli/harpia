## The Java DAO header names the child tables it doesn't persist

- **Depends on:** nothing (ordered after 1 to keep one golden move per task).
- **Deliverable:** `JavaDatabase/JavaCrudlAdapter.py` lists map / repeated
  fields (what `Database.model.map_fields()` / `repeated_fields()` would
  produce) in the "Deferred" header line next to the embed/FK columns,
  instead of `none`.
- **Golden move:** `UnitTests/golden_java/` DAO headers.
- **Tests:** `test_java_db_crudl.py` structural: `telemetry` / `shipment` /
  `data` headers name their child fields; `test_db_xlang3.py` can then derive
  Java's scope from the header instead of the Python DAO metadata (optional).
