## CRUDL DAO — map, repeated-scalar, repeated-FK link and repeated-composed child tables

- **Depends on:** task 2b.
- **Contract:** cover `map_fields()` / `repeated_fields()` from
  `Database/model.py`:
  - map → `<table>__<field>(owner, key, value)`;
  - repeated scalar → `(owner, ordinal, value)`;
  - repeated FK → link table storing each child's PK, with each child
    persisted via its DAO;
  - repeated-composed-to-table-less → one multi-column row per element;
  - the embed-nested variants (`<table>__<embed>_<field>`).

  Write order, delete-then-reinsert-on-update and read order all match C++
  `CrudlAdapter` (`_rep_write`/`_rep_read`/`_rep_composed_*`). After this
  task the "deferred" list from 2a is empty for every fixture message. A
  structural test asserts that.
- **Bar:** a C++-written row with child-table data reads back identically
  in Python, and the reverse.
- **Out of scope:** migrations of child tables (5b).
- **Tests:** generated-project round-trips for every child-table shape in
  the fixture; a g++-gated cross-read in both directions for one map
  message and one repeated-FK message.
