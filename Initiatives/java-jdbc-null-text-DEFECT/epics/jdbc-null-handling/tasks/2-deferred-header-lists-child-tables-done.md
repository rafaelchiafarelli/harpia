## The Java DAO header names the child tables it doesn't persist

- **Depends on:** nothing (ordered after 1 to keep one golden move per task).
- **1. Corroborate (red first):** add
  `UnitTests/test_java_db_crudl.py::test_deferred_header_names_child_fields`
  — generate, read the Java DAO for `telemetry` / `shipment` / `data`, assert
  the "Deferred" header names each map/repeated field. Must **fail** today
  (header says `none`). If it passes, record the finding and stop.
- **2. Fix:** `JavaDatabase/JavaCrudlAdapter.py` lists map / repeated fields
  (what `Database.model.map_fields()` / `repeated_fields()` produce) in the
  "Deferred" header line next to the embed/FK columns, instead of `none`.
- **3. Unit tests (required, kept):**
  - `test_deferred_header_names_child_fields` (above) — now green.
  - Existing `test_crudl_dao_notes_deferred_columns` stays green (embed/FK
    columns still listed).
- **Golden move:** `UnitTests/golden_java/` DAO headers; comment-only diff.
