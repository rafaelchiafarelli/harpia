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
  Task 2c: `ChildTable` specs (`CHILDREN`) cover every `map_fields()` /
  `repeated_fields()` shape: `map` (`owner, key, value`), `repeated`
  (`owner, ordinal, value`; with `fk` the value is each child's key and the
  child goes through its own DAO), `composed` (`owner, ordinal` + the
  element's flattened columns), and the embed-nested variants. Same order as
  C++: written after the main row (maps, then repeated), delete-then-reinsert
  on update, read in `ordinal` order by `read` and `list`, deleted by
  `remove`, dropped before the main table. `bind.to_db` / `from_db` convert
  one element / map key / map value by descriptor.

## Generated DAOs (`templates/dao.py.tmpl`)
`harpia_generated/db/<name>_<hash>_dao.py` per table-bearing message: class
`<name>_dao(Dao[<name>])` holding the table spec and the exact SQL. The DDL
is `Database.model.create_table_sql` (the very string the C++ DAO runs), so
the Python table has the **same column set C++ declares** (unlike Java's
scoped-down table); statements use `param_placeholder()`. Column order is
C++'s: scalar/enum/embedded columns, then FK columns. Embedded paths use the
exact `.proto` names (resolved from the schema; `Database.model.Column.embed`
holds C++'s lowercased accessors). The module
docstring lists anything the C++ DAO persists that this DAO does not
(`Deferred: ...`) — `none` for every fixture message since task 2c, asserted
by `test_nothing_deferred`.

## Registry (task 4, `templates/registry.py.tmpl`)
`harpia_generated/db/registry.py`: the port of `DbRegistryAdapter`'s
project-wide header, stdlib only — `Visibility`, `AccessDecision`,
`RegistryEntry`, `PROJECT_NAME` (from `ComplianceContext.project`), `REGISTRY`
(the very entries and `# note:` conflict lines `DbRegistryAdapter._entries()`
computes for C++), `find_entry`, `db_access_check(requesting_project,
table)` and its one-argument form (requesting project = `PROJECT_NAME`).
Another project loads it by path to check access; nothing enforces it in
the DAOs (C++ doesn't either).

## Migrations (tasks 5a + 5b)
`harpia_generated/migrate/<name>_<hash>_migrate.py` (`templates/migrate.py.tmpl`):
`migrate_<name>(conn, data_transform=None)` + `VERSION` + a `MigrationSpec`
whose every statement comes from the `DbBackend` — including the new
**migration plans** (`retype_plan`, `rep_child_plan`, `map_child_plan`,
`composed_child_plan`, `drop_column_sql` on `Database/backends`): the same
SQL the C++ `*_dynamic` methods embed, returned as data (those C++ methods
now build their SQL through the same private helpers; C++ output proven
byte-identical). `runtime/migrate.py` (`harpia_runtime.db.migrate`) runs the
C++ step order: version table → child renames → ensure tables → column
renames → ADD → `data_transform` → DROP → RETYPE → child reap + evolve →
stamp. One transaction (explicit `BEGIN` on `sqlite3`, whose DDL is otherwise
outside its implicit transactions); errors raise. Task 5b fills the child
steps from `MigrationAdapter._render`'s own sets: `child_renames` for
direct (non-embed-nested) repeated-scalar / map / repeated-composed fields
carrying `renamed_from` (embed-nested `renamed_from` isn't plumbed in C++
either), `child_current = child_table_names(...)` (so the reap runs in
every migrate module, `()` for a message with no child tables), and one
plan per repeated-scalar (no FK link table), map and repeated-composed
child table, with the backend's `int_type` as the owner type, as C++.
`child_current=None` (reap off) is still accepted by the engine but no
longer generated.

## phi encryption + audit (py-crypto-phi task 4, `runtime/phi.py`)
A message with a `phi` column gets a DAO subclassing
`harpia_runtime.db.phi.PhiDao` (else `Dao`, byte-unchanged) with
`PHI_FIELDS` and `Column(..., phi=True)`: constructor
`(conn, key_provider=None, audit_sink=None)` (defaults
`default_key_provider()` / `default_audit_sink()`); phi columns stored as
`encrypt_field` text (numbers stringified C++-style: `%f` floats, ints),
read back with `decrypt_field[_ll|_int|_float]` by field type (uint wrap,
bool); one `record("phi_<op>", table, "<phi cols>")` per `create`/`read`/
`update`/`remove` (`phi_delete`)/`list` — at C++'s points: not-found
`read` audits nothing, `update`/`remove` audit even when no row matched,
an FK child DAO audits its own ops with its own default provider (as C++).
`Dao` gained the no-op hooks `_bind`/`_load`/`_audit` that `PhiDao`
overrides. The adapter copies `phi.py` + the `harpia_runtime.crypto`
runtimes (column helper, interface, local + KMS backends) + the audit sink
only when some table-bearing message has a phi column (C++ CrudlAdapter's
set). Scope = C++'s: top-level / flattened-embed scalar columns only.
**C++ finding (task 4):** the shared DDL keeps a numeric phi column's
numeric type, so on PostgreSQL the `enc:v1:` text is rejected
(`patient_vitals.heart_rate` → `double precision`) — C++ and Python alike;
the PG round-trip test marks that case strict-xfail.

## Event OnChange (py-events task 2)
A table-bearing `event` message's DAO imports its
`harpia_generated.events.<name>_<hash>_events.<name>_channel` and overrides
`_on_change(msg)` to publish the written row (and, phi+event, record
`("phi_event_onchange", table, phi cols)` right after through the DAO's
`audit_sink`). `Dao._create` / `_update` call `_on_change` (so an FK child
written through its parent fires too, as C++'s child `create()` does);
nothing calls it from read / list / remove. An update of a missing row
still publishes (C++ publishes after any update).
**Decision (py-events task 2):** the publish is deferred with
`Dao._after_commit` to the commit of the outermost DAO transaction in the
current context (`contextvars`, shared by parent and child DAOs; dbio
imports included) and dropped on rollback — C++ autocommits per statement
and publishes inline, so its event never precedes an uncommitted write;
this keeps that property under Python's one-transaction-per-call.

## Bulk import/export (task 6, `templates/dbio.py.tmpl`)
`harpia_generated/dbio/<name>_<hash>_dbio.py` per table-bearing message (the
port of `DbIoAdapter`'s `dbio/<name>_<hash>_dbio.h`): `export_json(dao) ->
str`, `import_json(dao, text) -> int`, `export_xml(dao) -> str`,
`import_xml(dao, text) -> int` and `XML_WRAPPER` (`"<name>_list"`), thin
typed wrappers over `runtime/dbio.py` (`harpia_runtime.db.dbio`). Formats are
the C++ ones: NDJSON (one `to_json` per row + `\n`, blank lines skipped on
import) and `<name>_list` around one `to_xml` per row (every child element of
the root is a row, read with `from_xml_element`). For the same rows the XML
is byte-identical to C++ and every NDJSON line parses to the same message.
**Decision (task 6):** unlike C++ (`false`, keeping the rows already
created), the whole input is parsed first — malformed input raises
`ValueError` and writes nothing — and the rows are created in one
transaction (a duplicate key raises and rolls them all back). Imports return
the number of rows created.

## PostgreSQL (task 3)
`HARPIA_DB_BACKEND=postgresql` makes the generated DAOs run unchanged on a
`psycopg` connection: `%s` placeholders and PostgreSQL DDL come entirely
from `DbBackend`. `psycopg` is the generated project's optional
`postgres` extra. Opt-in test: `Docker/run_pg_tests.sh
UnitTests/test_python_db_postgres.py`.

## Key facts / gotchas
- **`list()` orders by the primary key** (decision at task 3). The C++ DAO's
  `list` has no `ORDER BY`, so its pages are unstable on PostgreSQL (rows
  come back in physical order, which an `UPDATE` changes); SQLite happens to
  return rowid = key order. Flagged to Rafael as a C++ finding.
- `limit=None` binds the largest 64-bit value, not `-1` (PostgreSQL rejects a
  negative `LIMIT`).
- PostgreSQL migration introspection (`information_schema`) is not
  schema-qualified, in C++ and Python alike: a same-named table in another
  schema leaks into the diff. The PG migration test uses a throwaway
  database. Flagged to Rafael.
- `users` and `top_users` share the table name `user_table` (the fixture's
  visibility collision): never create every DAO's table in one database.
- **Placeholders are dialect-baked at generation time** through
  `DbBackend.param_placeholder()` (decision at task 1, option (a)): `?` for
  `sqlite3`, `%s` for `psycopg`. Additive on the shared backend; C++ (SOCI
  `:name`) and Java (JDBC `?`) never call it, so their goldens are unchanged.
- A `composed` (repeated table-less message) element stores only its
  flattened scalar/enum columns: the element's hidden `ID_`/`STATUS_`/...
  fields don't round-trip (same as C++).
- The HarpiaTest fixture has no `bool`/`int64` fields (the DSL has no
  `bool`), so the bind test also compiles a small probe `.proto` with every
  scalar kind.

## Touchpoints
- Depends on: `Database/model.py`, `Database/backends` (`param_placeholder`),
  `PyAdapter.runtime_copy`.
- Tested by: `UnitTests/test_py_db_bind.py`, `test_py_db_dao.py`,
  `test_py_db_registry.py`, `test_py_db_migrate.py`,
  `test_py_db_migrate_children.py`, `test_py_db_dbio.py`, `test_py_db_phi.py`,
  `test_python_db_postgres.py` (opt-in).
