# PyDatabase — the Python target's database layer

**Pipeline role / purpose:** python-target / py-database. Copies the
hand-written DB runtime into the generated project
(`<dest>/python/harpia_runtime/db/`) and (from task 2a on) generates one
CRUDL DAO module per table-bearing message. Driven by the same
`Database/model.py` analysis and the same `DbBackend` object (`ctx.db_backend`)
as the C++ and Java targets, so all three agree on tables and columns.

**Entry point:** `PyDatabaseAdapter(messages, dest, backend, compliance).Process()`,
a stage of `LangBackend/python.py`'s `run_python`.

## Runtimes
- `runtime/bind.py` → `harpia_runtime.db.bind` (task 1): `bind_value(msg,
  field)` / `extract_value(row_value, msg, field)` for one scalar or enum
  field, dispatching on `FieldDescriptor.cpp_type` (exact `.proto` names, no
  accessor derivation). Integers, `bool` and enums bind as `int`, floats as
  `float`, strings as `str`; `NULL` reads back as the field default (like
  the C++ indicator check). Message/repeated fields raise `TypeError`.

## Key facts / gotchas
- **Placeholders are dialect-baked at generation time** through
  `DbBackend.param_placeholder()` (decision at task 1, option (a)): `?` for
  `sqlite3`, `%s` for `psycopg`. Additive on the shared backend; C++ (SOCI
  `:name`) and Java (JDBC `?`) never call it, so their goldens are unchanged.
- The HarpiaTest fixture has no `bool`/`int64` fields (the DSL has no
  `bool`), so the bind test also compiles a small probe `.proto` with every
  scalar kind.

## Touchpoints
- Depends on: `Database/model.py`, `Database/backends` (`param_placeholder`),
  `PyAdapter.runtime_copy`.
- Tested by: `UnitTests/test_py_db_bind.py`.
