### Session J.20 — ZMQ acceptance gate

- **Depends on:** J.18 merged (J.19 if it landed).
- **Acceptance gate:** ZMQ demo matches the C++ target's behavior for the
  same schema, CURVE-enabled and not.

## Implementation notes (landed 2026-08-23)

Genuinely nothing new, as scoped. The acceptance bar is already covered
by J.18/J.19's own tests, both of which exercise the same `HarpiaTest/
test.harpia` schema the C++ target's own ZMQ tests (`tests/
test_stage13_zmq.py`, `tests/test_demo.py`) use:

- `tests/test_java_zmq.py` — PUSH/PULL over `inproc://` (origin stamping
  confirmed) and PUB/SUB, both plaintext, same message shapes (`courier`
  push-only, `users` pull+push+event) the C++ demo/tests exercise.
- `tests/test_java_zmq_curve.py` — the CURVE case, over real `tcp://`
  (never `inproc://`, which is a no-op for CURVE on both targets):
  matching keys succeed, a wrong server public key times out rather than
  silently degrading to plaintext — the same two cases
  `test_stage13_zmq.py`'s own CURVE test asserts for C++.

Not run in this environment (no gradle/JDK here), same status as every
other Java integration test this thread has added — this session doesn't
change that, it just confirms there's no additional gap to close beyond
what J.18/J.19 already built and tested.

Same deferred-scope reminder as every other acceptance gate in this
thread: this is the ZMQ surface for what J.18/J.19 actually built, not a
claim that every C++ ZMQ behavior (e.g. the demo's CURVE keygen probe
tooling, `USAGE.md` §10) has a Java equivalent yet.