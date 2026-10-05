# Java DAO can't read a NULL text column — DEFECT

**Status: scoped, not started.** Found 2026-10-04 (python-target
`tri-language-interop/2`; decisions log item 44 in
`Initiatives/python-target/NEXT_SESSION.md`). Not fixed: it moves
`golden_java/`.

## What was found

`JavaDatabase/runtime/JdbcBind.java`, `extract()` (~line 75):

```java
case STRING:
    builder.setField(fd, rs.getString(columnLabel));
```

`getString` returns `null` for SQL NULL and protobuf's `setField` throws
`NullPointerException`. C++ and Python read NULL as the default (`""`).

When it bites: any row that predates a C++/Python migration has NULL in every
column the migration added (e.g. `beacon_log`'s
`STATUS_`/`ERROR_`/`ORIGINATOR`) — the Java DAO can't `read`/`list` it at all.
Pinned as strict xfails in `test_db_xlang3.py`
(`test_*_java_reads_pre_migration_row`, SQLite + PG).

Related (same module, documentation-level): the generated Java DAO's
"Deferred columns" header lists only embed/FK columns; a message whose
map/repeated fields live in child tables (`telemetry`, `shipment`, `data`'s
maps) says `none` even though Java never reads or writes those child tables.

## Scope

One epic: **`jdbc-null-handling`**. **Moves `UnitTests/golden_java/`** (the
runtime and DAO headers are snapshotted). See `epics/README.md`.
