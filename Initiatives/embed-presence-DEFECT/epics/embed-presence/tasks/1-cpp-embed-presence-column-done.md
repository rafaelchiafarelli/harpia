## C++: a hidden presence column per embedded message field

- **Depends on:** the decisions in `../../README.md`.
- **Contract:** `Database/model.py` `analyze()` emits, for each flattened
  embed level (prefix=True), a hidden bindable INTEGER `Column`
  `HARPIA_HAS_<prefix>` (marked as an embed-presence column with its embed
  path), placed before that embed's sub-columns. The SQL schema, migration
  (ADD COLUMN, existing rows NULL) and C++ DAO pick it up: write binds
  `has_<embed>()` (chained) as 1/0 and binds the embed's sub-columns NULL
  when it is absent; read evaluates presence top-down and only touches
  `mutable_<embed>()` when the presence column is NULL or 1.
- **1. Corroborate (red first):**
  `test_stage8_db.py::test_embed_presence_round_trip` — `data` with `val`
  unset reads back `!has_val()`; with `val` set to an all-default `prince`
  reads back `has_val()`; a row whose `HARPIA_HAS_val` is NULL reads present.
  Fails today (unset reads present).
- **2. Fix:** `Database/model.py`, `Database/CrudlAdapter.py` (+ SqlAdapter /
  MigrationAdapter through the shared columns).
- **3. Unit tests (kept):** the red test + a PG twin in `test_stage8_pg.py`;
  a nested-embed case on `journey` (`path.start`).
- **Golden move:** every message with an embedded message field (db, migrate,
  sidecars/database, Python DDL copies).
