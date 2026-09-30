## Java CURVE client against a C++ ZAP-allowlisted publisher

- **Depends on:** nothing (can run in parallel with tasks 1–2).
- **Contract:** no new API unless the test proves one is needed.
  `HarpiaZmq.CurveKeys` (J.19) must interoperate with a hardened C++ PUB whose
  ZAP handler enforces `HARPIA_ZMQ_ALLOWLIST`. If the Java side needs a change
  to be accepted (e.g. it has to set a ZAP domain or identity), that change is
  this task's contract, and it's documented in `JavaZmqAdapter/CLAUDE.md`.
- **Pre-work:** none; reuse the cross-language harness from
  `UnitTests/test_zmq_xlang_pubsub_fanout.py`.
- **Out of scope:** Android (task 4), Java-side ZAP *server* (Java servers stay
  unhardened, initiative non-goal).
- **Tests:** C++ PUB (CURVE + ZAP) → Java SUB: an allowlisted client key
  receives; an unknown key receives nothing and the C++ side writes one
  `zap_denied` audit record; a wrong server public key times out (never
  falls back to plaintext).
