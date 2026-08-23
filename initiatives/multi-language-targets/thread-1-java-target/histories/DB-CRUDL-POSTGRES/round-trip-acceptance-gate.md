### Session J.9 — Postgres round-trip acceptance gate

- **Depends on:** J.8 merged.
- **Deliverable:** nothing new — closes the loop for Postgres.
- **Tests:**
  - Integration: full CRUDL cycle against a real `postgres` container,
    same posture as the C++ Postgres-on-Windows resolution.
- **Acceptance gate:** this session is the acceptance gate.