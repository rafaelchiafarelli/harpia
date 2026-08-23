### Session J.5 — DB package scaffolding + JDBC bind/extract primitives

- **Depends on:** J.2 merged.
- **Deliverable:** new Java DB package reusing `Database/model.py`'s
  language-agnostic `analyze()`/`map_fields()`/`repeated_fields()` IR
  as-is; JDBC bind/extract (`PreparedStatement.setInt/setString/setLong`
  / `ResultSet.getInt/getString`) as the structural analogue of SOCI's
  `use()`/`into()`; `org.xerial:sqlite-jdbc` driver (pure JDBC, bundles
  native SQLite per-platform, no source-vendoring needed).
- **Out of scope:** CRUDL operations themselves (J.6); migration support
  (flagged out of scope below, not part of this track's first pass).
- **Tests:**
  - Unit: bind/extract round trip per supported type.