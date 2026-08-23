### Session J.27 — Android verification: ZMQ client + track acceptance gate

- **Depends on:** J.24 merged; J.18 (ZMQ core) merged.
- **Deliverable:** verified on an actual Android build: ZMQ client
  (JeroMQ, unverified specifically on Android vs. desktop/server JVM
  until this session).
- **Out of scope:** DB/CRUDL, REST/SOAP servers, gRPC service impl — not
  consumed on-device at all (a phone doesn't host these).
- **Tests:**
  - Integration: a real Android build exchanging a message over ZMQ.
- **Acceptance gate:** this is the *track's* actual "done" bar per
  `../../README.md` §8 — not just "Java target builds and passes its own
  tests," but "the Android consumption path was verified for real,"
  across message classes (J.25), gRPC (J.26), and ZMQ (this session).