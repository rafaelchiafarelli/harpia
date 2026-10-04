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

- `runtime/dao.py` → `harpia_runtime.db.dao` (task 2a): the CRUDL engine.
  `Dao[M]` implements `create_table` / `drop_table` / `create(msg) -> bool` /
  `read(pk, out) -> bool` / `update(msg) -> bool` / `remove(pk) -> bool` /
  `list(offset=None, limit=None)` from class-level data a generated DAO
  declares (`MESSAGE`, `TABLE`, `PK`, `COLUMNS` of `Column(name, path)`, and
  every SQL string). `Connection` / `Cursor` are DB-API `Protocol`s.
  Real DB errors raise; a `bool` only answers "row existed / affected".
  Each call is one transaction (commit on success, rollback on error).
  Task 2b: `Column.path` reaches flattened embedded sub-fields through any
  number of table-less levels (`("path", "start", "city")`); `Column.fk`
  (`"module:Class"`, resolved lazily so DAOs may refer to each other) marks
  an FK column holding the child's primary key — a present child is written
  through its own DAO first (create/update), a non-zero key loads it on
  read, a zero key leaves it absent, `remove` does not cascade (all as C++).
  Child DAOs run on the parent's cursor, so a whole call is still one
  transaction (stricter than C++, which commits per statement).

## Generated DAOs (`templates/dao.py.tmpl`)
`harpia_generated/db/<name>_<hash>_dao.py` per table-bearing message: class
`<name>_dao(Dao[<name>])` holding the table spec and the exact SQL. The DDL
is `Database.model.create_table_sql` (the very string the C++ DAO runs), so
the Python table has the **same column set C++ declares** (unlike Java's
scoped-down table); statements use `param_placeholder()`. Column order is
C++'s: scalar/enum/embedded columns, then FK columns. Embedded paths use the
exact `.proto` names (resolved from the schema; `Database.model.Column.embed`
holds C++'s lowercased accessors). The module
docstring lists anything the C++ DAO persists that this DAO does not yet
(`Deferred: ...`).

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
