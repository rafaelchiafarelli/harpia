### Session J.17 — Confirm JeroMQ CURVE support

- **Depends on:** nothing (pure verification, can run any time).
- **Deliverable:** a confirmed answer, against a pinned JeroMQ version,
  to whether CURVE is actually supported — `../../README.md` §2 flags this
  as an unconfirmed claim, same discipline this repo applied to the
  SOCI::PostgreSQL alias question before assuming an answer. Blocks J.19,
  nothing else.
- **Tests:** the verification itself — a minimal CURVE handshake against
  the pinned JeroMQ version, pass/fail.