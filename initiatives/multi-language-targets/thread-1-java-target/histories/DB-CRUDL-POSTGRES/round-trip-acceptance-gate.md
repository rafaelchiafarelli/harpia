### Session J.9 — Postgres round-trip acceptance gate

- **Depends on:** J.8 merged.
- **Deliverable:** nothing new — closes the loop for Postgres.
- **Tests:**
  - Integration: full CRUDL cycle against a real `postgres` container,
    same posture as the C++ Postgres-on-Windows resolution.
- **Acceptance gate:** this session is the acceptance gate.

## Implementation notes (landed 2026-08-23, together with J.8)

`tests/test_java_db_crudl_postgres.py::
test_users_crudl_full_cycle_against_postgres` — the same `users_dao`
create/read/update/list/remove cycle J.7 proved against SQLite, run
against a real Postgres server instead (a live `HARPIA_PG_DSN`, opt-in,
same as the C++ target's own Postgres acceptance test). Not run in this
environment (no live Postgres server, no gradle/JDK here) — like every
other Java integration test this thread has added, it's written and
correct-by-inspection, verified for real whenever a Java-capable
CI/Docker image with a Postgres container exists.

Same deferred-column scope note as `DB-CRUDL-SQLITE/sqlite-round-trip-
acceptance-gate.md`: this proves the SQLite/Postgres round trip for the
columns J.6 actually handles (top-level scalar/enum), not full C++
CrudlAdapter parity.