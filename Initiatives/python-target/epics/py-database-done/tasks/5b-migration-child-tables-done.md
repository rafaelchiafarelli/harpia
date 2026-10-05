## Schema migration — child tables (rename, orphan reap, per-shape evolution)

- **Depends on:** task 5a.
- **Contract:** extend `migrate_<name>` with the child-table steps
  `MigrationAdapter` performs:
  - rename `<table>__<old>` → `<table>__<new>` for `renamed_from` on
    repeated/map fields, **before** ensure/create;
  - reap any live `<table>__*` table that is not in
    `model.child_table_names()`;
  - evolve each surviving child table: repeated-scalar `value` retype, map
    `key`/`value` retype, and repeated-composed full ADD/DROP/RETYPE of the
    data columns (`owner`/`ordinal` kept).

  This is emitted in every migrate module, so the orphan reap runs even for
  a message with no child tables left.
- **Bar:** same end state as the C++ migration from the same starting
  database.
- **Out of scope:** nothing beyond C++ parity. Embed-nested `renamed_from`
  isn't plumbed in C++ either; say so in the docstring.
- **Tests:** schema-evolution tests per child-table shape (SQLite, plus
  Postgres opt-in); a g++-gated C++-v1 → Python-v2 case with a map field.
