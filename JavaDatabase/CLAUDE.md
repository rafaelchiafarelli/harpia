# JavaDatabase — Java target: JDBC bind/extract runtime + CRUDL DAO generation

**Pipeline role:** Java-target Stage 8 equivalent (sessions J.5/J.6/J.7, `initiatives/multi-language-targets/thread-1-java-target`, landed together — see their history files). Reuses `Database/model.py`'s language-agnostic `type_registry()`/`analyze()` IR as-is to derive columns, then generates a per-table-bearing-message CRUDL DAO against a reflection-based JDBC bind/extract runtime.
**Entry points (from main.py):** both gated behind `HARPIA_GEN_LANG=java`, called right after `JavaJsonAdapter` in the same block, sharing the SAME `dbBackend` the C++ Stage-8 calls later in `main.py` use (resolved once, moved earlier in the file for this reason):
- `JavaDbAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()` — ships the runtime.
- `JavaCrudlAdapter(messages=msgFactory.messages, dest=testDestination, backend=dbBackend, compliance=complianceContext).Process()` — generates the DAOs.
Both return `None` or an `Error` (non-fatal; main.py logs it).
**Inputs → Outputs:** `JavaDbAdapter` emits `<dest>/java/src/main/java/com/harpia/runtime/db/JdbcBind.java`. `JavaCrudlAdapter` emits `<dest>/java/src/main/java/com/harpia/generated/db/<name>_dao.java` for every message with a `tableName`.

## Files
- `runtime/JdbcBind.java` — hand-written (NOT generated), copied verbatim by `JavaDbAdapter`. Two static methods, `bind(PreparedStatement, int index, Message msg, String fieldName)` and `extract(ResultSet, String columnLabel, Message.Builder builder, String fieldName)`, both dispatching on `FieldDescriptor.getJavaType()` (INT/LONG/FLOAT/DOUBLE/STRING/ENUM). **Reflection-based, not typed accessors — this is the key design decision, see below.**
- `JavaDbAdapter.py` — J.5. `Process()` just copies `runtime/JdbcBind.java` in. No per-message logic (the runtime is message-agnostic, same shape as `JavaJsonAdapter`).
- `JavaCrudlAdapter.py` — J.6. `Process()` calls `Database.model.type_registry(messages)` once, then per table-bearing message `Database.model.analyze(msg, types, self.backend)` to get `(columns, notes)`. Splits `columns` into `usable` (no `.embed`, no `.fk_table` — i.e. every column `JdbcBind` can actually bind/extract by its own `.proto` field name) and `deferred` (everything else); logs each deferred column and lists it in the generated DAO's own header comment, never silently drops it. Builds SQL strings directly in Python (`self.backend.create_table(...)`/`.drop_table(...)` for DDL — reusing the SAME `DbBackend` methods `Database/SqlAdapter.py` uses, just fed a filtered column list — see "Scoped-down schema" below) and renders `templates/dao.java.tmpl`.
- `templates/dao.java.tmpl` — one Java class per message, `com.harpia.generated.db.<name>_dao`: `createTable()`/`dropTable()`, `create(msg)`, `read(pkValue, builder)`, `update(msg)`, `remove(pkValue)`, `list(List<out>)`. Every non-PK bind/extract call goes through `JdbcBind`; the PK parameter itself uses a plain `PreparedStatement.set<Kind>`/none needed for extraction (PK comes back through `JdbcBind.extract` like any other column, in `read`/`list`).

## Why reflection, not typed accessors (the load-bearing design decision)
A generated DAO calling typed accessors (`msg.getPatientId()`, mirroring how a human would write JDBC code) requires knowing, at Python generation time, exactly what Java identifier `protoc`'s Java plugin will derive from a `.proto` field name — protobuf's real `UnderscoresToCamelCase` algorithm (case-by-case: lowercase letters capitalize on a `cap_next` flag, uppercase letters pass through unchanged past position 0, digits pass through AND set `cap_next`, any other character sets `cap_next` and is dropped). Hand-reproducing that exactly, for **every** field name harpia's front-end can produce — including the hash-suffixed `ID_<hash>`/`STATUS_<hash>`/`ERROR_<hash>` fields injected into every single message — is a real, easy-to-get-subtly-wrong risk, and this repo has no `protoc`/JDK on the generation host (or in CI here) to catch a mistake by actually compiling the result.

`Descriptors.FieldDescriptor.findFieldByName(name)` sidesteps the entire problem: it looks a field up by its **exact, unmodified `.proto` field name** — which harpia already knows with total certainty, because it's the same string `FileCreator.py` wrote into the `.proto` in the first place (`Column.name`, for every column this session handles, IS that exact name — see `protoFile/CLAUDE.md`). `Message.getField(fd)`/`Builder.setField(fd, value)` then read/write generically off that descriptor, no method-name derivation anywhere. This is the same reflection-based strategy the future XML session (J.10/J.11) already plans to use (`../../README.md` §2's XML row) — DB just gets there first.

## Deliberately reduced scope (flagged, not scoped here — like schema migration)
Only top-level scalar/enum columns (`analyze()` output where `Column.embed` is `None` and `Column.fk_table` is `False`) are handled:
- **Handled:** every plain scalar/enum column `analyze()` returns for a table-bearing message, INCLUDING the front-end-injected `ID_<hash>`/`STATUS_<hash>`/`ERROR_<hash>`/`ORIGINATOR` fields (they're plain top-level `STRING` columns, no different from a schema-authored one — see the real `user_table` schema in `tests/golden/sidecars/database/`).
- **Deferred:** a singular composed field whose target owns a table (`fk_table` — e.g. `top_users.myUsers`), a flattened embed column (`embed` set — e.g. `journey.path.label`), and everything `map_fields()`/`repeated_fields()` would produce (map/repeated child tables) — `JavaCrudlAdapter` never even calls those two functions. A message whose *every* declared field falls into one of these categories still gets a DAO — with just the front-end-injected columns (PK + STATUS_/ERROR_/ORIGINATOR).
- This mirrors the "flagged, not scoped here" treatment `DB-CRUDL-SQLITE/sqlite-round-trip-acceptance-gate.md` already gives schema-evolution/migration support — the C++ `CrudlAdapter` this reuses IR from took its own long incremental history to grow this sophistication (`Database/CLAUDE.md`); replicating all of it in one sitting was never this session's bar.

## Scoped-down schema (a real, deliberate difference from the C++ target's table)
`JavaCrudlAdapter`'s `CREATE_TABLE_SQL` declares **only** the `usable` columns — NOT the full schema `Database/SqlAdapter.py` already writes to `<dest>/database/<name>_<hash>_table.sql` for the C++ target (unconditionally, regardless of `HARPIA_GEN_LANG`). Reusing that full schema instead would mean the Java DAO's `INSERT` violates a `NOT NULL` constraint on any `REQUIRED` deferred column it never binds. So for a message with any deferred column, **the Java target's own SQLite table has fewer columns than the C++ target's table of the same name** — self-consistent on its own terms, a real and disclosed divergence, not a bug. `users`/`beacon_log`/`crew`/`patient_vitals` (all-scalar messages) have no deferred columns, so their Java and C++ schemas match exactly.

## Key facts / gotchas
- `dbBackend` is resolved once in `main.py`, **before** the `HARPIA_GEN_LANG` block (moved there from its original spot next to the C++ Stage-8 calls) specifically so both targets share the identical `DbBackend` for a given run — `HARPIA_DB_BACKEND=postgresql` picks Postgres for both, not just C++.
- The primary-key column's Java parameter type (`read(int id, ...)`/`remove(int id)`) is derived from `pk.kind` via a `kind -> Java primitive` map, not hardcoded to `int` — in practice it's always `int` (every `ID_<hash>` is `INT32` per the front-end's own injection, confirmed against the golden `.proto` output), but deriving it keeps the generator correct if that ever changes rather than silently wrong.
- `create()`/`update()` bind the PK explicitly, matching the C++/SOCI convention (`Database/backends/sqlite.py`'s `column_def()`: "Caller-assigned PK... The id is set by the caller and bound on INSERT, so no auto-generation is introduced") — the DB never assigns it.
- DAO methods return `boolean` (found/not-found, or insert/update affected a row) but let `SQLException` propagate on a real error, rather than swallowing it into a `false` return the way the C++/SOCI side's `try`/`catch`-wrapped bool return might read at a glance — a deliberate Java-idiom choice (checked exceptions for real failures, boolean only for the affirmatively boolean "did a row exist" question), not an attempt to mirror the C++ signature byte for byte.

## Touchpoints
- Called by: `main.py`, gated on `HARPIA_GEN_LANG=java`, right after `JavaJsonAdapter` in the same conditional block; `JavaCrudlAdapter` additionally needs `dbBackend` (see above).
- Depends on: `Database.model` (`type_registry`, `analyze` — NOT `map_fields`/`repeated_fields`, not called this session), `Database.backends.DbBackend` (`create_table`/`drop_table`/`column_def` — via `Column.sql_def()`), `Util.util.write_if_different`/`copy_if_different`/`loadTemplate`, `Logger.logger`, `Errors.Error`.
- Consumed by: whichever future session lifts the embed/FK/map/repeated deferral — that's extending `JavaCrudlAdapter`'s column filter, not a new adapter.

## Postgres (J.8/J.9)

Confirmed exactly as predicted above: J.8's entire wiring is
`GradleAdapter/templates/project.gradle.tmpl` gaining `implementation
'org.postgresql:postgresql:42.7.3'` (pure Java, no native library at all,
unlike C++'s `libpq`) — zero changes to `JavaCrudlAdapter.py` or
`dao.java.tmpl`, because a generated DAO only ever holds a plain
`java.sql.Connection` and reads `Column.sql_def()`/`self.backend.
create_table()` from whichever `DbBackend` `main.py` resolved
(`Database/backends/postgres.py`: same caller-assigned-PK convention as
SQLite, same neutral bind kinds — only the SQL type strings differ, e.g.
`INT64`→`BIGINT`, `FLOAT`→`DOUBLE PRECISION`). `tests/
test_java_db_crudl_postgres.py` is opt-in (`HARPIA_PG_DSN` + gradle/JDK),
same posture as `tests/test_stage8_pg.py` on the C++ side — parses the
same libpq-style DSN into a JDBC URL rather than introducing a parallel
Postgres-config mechanism.
