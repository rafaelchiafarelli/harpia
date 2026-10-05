## CRUDL DAO — flattened embeds (multi-level) + singular FK-to-table

- **Depends on:** task 2a.
- **Contract:** extend the DAO generator to cover:
  - `Column.embed` chains, including multi-level `["path","start"]`,
    bound and extracted through the nested sub-message
    (`msg.path.start.city`);
  - `fk_table` columns, where the child is persisted and loaded through
    the child's own generated DAO (C++ `_fk_hooks`/`_fk_extract`
    semantics). An absent child stays absent: no phantom row.

  This includes FK-inside-embed, which C++ supports through `_flatten()`'s
  `kind == "table"` branch.
- **Bar:** behavior matches C++ `CrudlAdapter` for every fixture message
  with embed/FK fields (e.g. `journey.path.*`, `top_users.myUsers`). A row
  written by C++ reads back identically in Python.
- **Out of scope:** child tables (2c).
- **Tests:** generated-project round-trips for the embed/FK fixture
  messages, including an unset FK; a g++-gated C++→Python cross-read for
  one embed and one FK message.
