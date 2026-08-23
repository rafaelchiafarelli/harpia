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