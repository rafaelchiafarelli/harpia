## Generated CRUDL DAO — scalar/enum columns, DDL, paginated list

- **Depends on:** task 1.
- **Contract:** a `PyCrudlAdapter` (under the python backend) calls
  `Database.model.type_registry()` / `analyze(msg, types, dbBackend)` and
  emits `harpia_generated/db/<name>_<hash>_dao.py` per table-bearing
  message with a class `<name>_dao(conn)`:
  - `create_table()` / `drop_table()`, with DDL from `dbBackend` and the
    **same column set C++ declares** (unlike Java's scoped-down table);
  - `create(msg) -> bool`;
  - `read(pk, out) -> bool`;
  - `update(msg) -> bool`;
  - `remove(pk) -> bool`;
  - `list() -> list[msg]` and paginated `list(offset, limit)`.

  The PK is caller-assigned and bound explicitly (C++/SOCI convention).
  Real DB errors propagate as exceptions; `bool` answers only "did a row
  exist / was one affected". This task emits non-scalar columns as an
  explicit `# deferred to task 2b/2c` list in the generated header
  docstring, and that list must be empty when 2c lands.
- **Bar:** the SQL schema a Python DAO creates is identical to
  `<dest>/database/<name>_<hash>_table.sql` for all-scalar messages.
- **Out of scope:** embed/FK (2b), map/repeated (2c), phi (`py-crypto-phi`
  task 4), event publish (`py-events` task 2).
- **Tests:**
  - Golden snapshot.
  - Generated-project CRUDL round-trip per all-scalar fixture message
    (`users`, `beacon_log`, `crew`, `patient_vitals`), including
    pagination bounds.
  - A g++-gated check that a row written by the C++ DAO reads back
    identically through the Python DAO on the same SQLite file.
