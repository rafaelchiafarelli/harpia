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

## Implementation notes (landed 2026-08-23) — written, NOT run; acceptance gate NOT met yet

`examples/android_consumer/app/src/androidTest/.../ZmqClientAndroidTest.
java`: a PUSH/PULL round trip over `inproc://` using `courier_zmq`
(J.18's generated factory) and `HarpiaZmq` — deliberately self-contained
(no external server/network) so it isolates exactly the fact in question:
whether JeroMQ's pure-Java ZMTP implementation runs on Android's ART
runtime at all, the one thing `../../README.md` §7 flags as genuinely
unconfirmed on-device specifically (unlike message classes/JSON/gRPC,
whose Android-suitability is a matter of settled Android practice, not an
open question).

**Track acceptance gate status: written, not met.** This session's own
bar — "the Android consumption path was verified for real" — requires an
actual device/emulator run of all three `examples/android_consumer`
tests, which has not happened (no Android SDK in this environment,
flagged plainly in `examples/android_consumer/README.md`'s verification-
status section). **This is the one honest gap left in this thread as of
2026-08-23**: every other session (J.1-J.24) has real, working,
Python-side-tested code; J.25-J.27 have real, carefully-written Android
code that has genuinely never been compiled or run. Whoever picks up
Android tooling next should treat running `examples/android_consumer`
for real as the literal remaining item to close this track out, not
re-derive it from scratch.