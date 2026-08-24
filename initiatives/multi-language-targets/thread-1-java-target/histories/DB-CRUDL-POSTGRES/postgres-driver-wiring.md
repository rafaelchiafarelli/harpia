### Session J.8 — Postgres driver wiring

- **Depends on:** J.7 merged — reuses J.5's backend seam.
- **Deliverable:** `org.postgresql:postgresql` driver (pure Java, no
  native library at all, unlike C++'s `libpq`) wired into the same
  bind/extract seam J.5 established.
- **Tests:**
  - Unit: bind/extract round trip per supported type, against Postgres'
    JDBC driver specifically (type-mapping differences from SQLite, if
    any, surface here).

## Implementation notes (landed 2026-08-23)

Confirmed the prediction `JavaDatabase/CLAUDE.md` made while J.5/J.6 were
still being written: wiring Postgres is **only**
`GradleAdapter/templates/project.gradle.tmpl` gaining `implementation
'org.postgresql:postgresql:42.7.3'`. Zero changes to `JavaCrudlAdapter.py`
or `templates/dao.java.tmpl` — a generated DAO only ever holds a plain
`java.sql.Connection` and reads SQL from whichever `DbBackend` `main.py`
resolved via `HARPIA_DB_BACKEND` (shared with the C++ target, same env
var, same object — see `JavaDatabase/CLAUDE.md`'s `dbBackend` note), so
Postgres's own dialect (`Database/backends/postgres.py`: `INT64`→`BIGINT`,
`FLOAT`→`DOUBLE PRECISION`, same caller-assigned-PK convention as SQLite)
was already reachable through the seam J.5 established.

Test: `tests/test_java_db_crudl_postgres.py`, opt-in (`HARPIA_PG_DSN` +
gradle/JDK), same posture as the C++ target's `tests/test_stage8_pg.py`.