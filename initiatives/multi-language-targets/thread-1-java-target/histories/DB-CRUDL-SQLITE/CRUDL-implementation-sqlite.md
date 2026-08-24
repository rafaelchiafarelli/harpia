### Session J.6 — CRUDL implementation, SQLite

- **Depends on:** J.5 merged.
- **Deliverable:** create/read/update/delete/list operations on SQLite,
  built on J.5's bind/extract primitives.
- **Tests:**
  - Integration: full CRUDL cycle against SQLite.

## Implementation notes (landed 2026-08-23, together with J.5/J.7)

New `JavaDatabase/JavaCrudlAdapter.py`, one `<name>_dao.java` per
table-bearing message. Reuses `Database.model.type_registry()`/`analyze()`
as-is (this session's own deliverable text) to get columns; every
non-embed/non-FK column goes through J.5's `JdbcBind`.

**Scope deliberately narrower than C++'s CrudlAdapter, flagged (not
silently assumed) in `JavaDatabase/CLAUDE.md`:** only top-level scalar/enum
columns are handled this session. A singular FK-to-a-table field
(`fk_table`), a flattened-embed field (`embed`), and every
`map_fields()`/`repeated_fields()` child table are deferred -- logged and
listed in the generated DAO's own header comment, never silently dropped.
The generated `CREATE TABLE` is scoped to match (only the columns this DAO
actually populates), which means the Java target's own SQLite schema for a
message with deferred columns is genuinely smaller than the C++ target's
schema for the same table -- see `JavaDatabase/CLAUDE.md`'s "Scoped-down
schema" section for why (a REQUIRED deferred column would otherwise violate
NOT NULL on every INSERT this DAO issues).

`users` (`HarpiaTest/test.harpia`: `address`/`name`, both plain strings) is
an all-scalar table, so its Java DAO's schema matches the C++ target's
exactly, with a complete (not partial) CRUDL surface -- the fixture for
J.7's acceptance-gate round trip.

Tests: `tests/test_java_db_crudl.py`.