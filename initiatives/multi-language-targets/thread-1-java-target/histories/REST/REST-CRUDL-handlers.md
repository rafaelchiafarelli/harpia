### Session J.13 — REST CRUDL handlers

- **Depends on:** J.12 merged; J.6 (SQLite CRUDL) merged.
- **Deliverable:** REST handlers wired to J.6's DB layer — create/read/
  update/delete/list over HTTP.
- **Tests:**
  - Integration: live REST CRUDL calls against the generated Java server.

## Implementation notes (landed 2026-08-23, together with J.12/J.14)

New `JavaRestAdapter/templates/rest.java.tmpl`, one `<name>_rest.java` per
table-bearing message, wiring `list`/`read`/`create`/`update`/`remove`
straight into J.6's `<name>_dao` and content-negotiating via the already-
generic `HarpiaJson`/`HarpiaXml`.

**Scope reduction, a direct consequence of J.6's own** (flagged in
`JavaRestAdapter/CLAUDE.md`): `list()` is unpaginated. J.6 never built the
C++ target's paginated `list(out, offset, limit)` DAO overload, so there's
nothing for a `?limit=`/`?offset=` query parameter to call yet — not a new
independent gap, just this one surfacing where J.6's already-disclosed
reduction is visible from the REST side.

Tests: `tests/test_java_rest.py`.
