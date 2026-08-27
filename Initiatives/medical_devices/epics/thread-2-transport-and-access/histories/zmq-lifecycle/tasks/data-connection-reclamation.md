## Session B.2 — Dead-connection reclamation

- **Depends on:** B.1 merged.
- **Deliverable:** abandoned connections reclaimed within a configured
  window. Mind the `ZMQ_LINGER` gotcha above — a socket abandoned
  mid-handshake will hang on destruction under the default `-1` linger
  unless this is handled explicitly.
- **Tests:**
  - Integration: extend the existing demo test with a dead-connection
    scenario (socket abandoned mid-handshake), confirm reclamation within
    the configured window and no hang on destruction.
