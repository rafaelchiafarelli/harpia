### Session J.8 — Postgres driver wiring

- **Depends on:** J.7 merged — reuses J.5's backend seam.
- **Deliverable:** `org.postgresql:postgresql` driver (pure Java, no
  native library at all, unlike C++'s `libpq`) wired into the same
  bind/extract seam J.5 established.
- **Tests:**
  - Unit: bind/extract round trip per supported type, against Postgres'
    JDBC driver specifically (type-mapping differences from SQLite, if
    any, surface here).