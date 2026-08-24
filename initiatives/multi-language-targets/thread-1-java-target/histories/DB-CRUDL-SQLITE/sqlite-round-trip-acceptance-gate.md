### Session J.7 — SQLite round-trip acceptance gate

- **Depends on:** J.6 merged.
- **Deliverable:** nothing new — closes the loop, verifying the full
  write/read/CRUDL surface built in J.5–J.6 works together end to end.
- **Tests:**
  - Integration: write → persist → restart process → read; confirm
    values match, mirroring the C++ target's own CRUDL golden tests
    (14.1/14.2).
- **Acceptance gate:** this session is the acceptance gate.

**Flagged, not scoped here:** schema-evolution/migration support is
explicitly **out of scope for this track's first pass** — `java-target.md`'s
original per-stage table didn't call it out as day-one scope, and adding
it here would be inventing scope the source material didn't commit to.
Follow-on work, if needed.

## Implementation notes (landed 2026-08-23, together with J.5/J.6)

Genuinely "nothing new," as scoped: no additional production code. The
acceptance-gate test (`tests/test_java_db_crudl.py::
test_sqlite_round_trip_survives_process_restart`) writes a `users` row via
one `java` subprocess invocation, closes the connection, then reads it
back via a **separate** `java` subprocess invocation against the same
SQLite file path — proving the data actually persisted to disk rather than
just staying alive in the writer JVM's memory, the literal "restart
process" bar this session's spec calls for.

**Also flagged here** (beyond migration, already flagged above): the
embed/singular-FK-to-table/map/repeated-column deferral J.6 introduced
(`JavaDatabase/CLAUDE.md`) is this track's own scope reduction, not
inherited from `java-target.md` — worth restating at the acceptance gate
so a future session doesn't read "SQLite round-trip acceptance gate: done"
as "full C++ CrudlAdapter parity: done."