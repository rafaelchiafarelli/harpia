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

## Implementation notes (landed 2026-08-23, together with J.6/J.7)

New `JavaDatabase/` package. `runtime/JdbcBind.java` (hand-written) is
**reflection-based**, not typed-accessor-based like the sketch above's
literal `PreparedStatement.setInt/setString/setLong` reads — `Descriptors
.FieldDescriptor.findFieldByName(<exact .proto field name>)` +
`Message.getField(fd)`/`Builder.setField(fd, value)` sidesteps needing to
predict protoc's camelCase Java accessor derivation at Python-generation
time (unverifiable without a JDK/protoc on this host) for every field,
including the hash-suffixed `ID_<hash>`/`STATUS_<hash>`/`ERROR_<hash>`
front-end-injected ones. Full rationale in `JavaDatabase/CLAUDE.md`.
`org.xerial:sqlite-jdbc:3.45.1.0` wired into `build.gradle`.

Tests landed as part of `tests/test_java_db_crudl.py` (covers J.5/J.6/J.7
together) — see that session's own notes for why they weren't split
three ways.