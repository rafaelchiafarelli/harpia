# Track J — Java target: remaining work

J.1–J.24 (proto/gRPC wiring, JSON, DB×2 dialects, XML, REST, SOAP, ZMQ
core+CURVE, generated JUnit tests, Gradle packaging, protobuf-runtime
decision) **shipped** — real code, real Python-side tests, matching
commits `d662450`..`c46d704`. Each module documents its own shipped
design in its own `CLAUDE.md` (`GradleAdapter/`, `JavaDatabase/`,
`JavaJsonAdapter/`, `JavaXmlAdapter/`, `JavaRestAdapter/`,
`JavaSoapAdapter/`, `JavaZmqAdapter/`, `JavaTestAdapter/`) — read those,
not a deleted history file, for how any of it works. See
`../README.md`'s status header for the full picture, including the one
caveat that survives from that work: the gradle+JDK-gated Java-side
tests are written correctly-by-inspection but have never executed
against a real JVM toolchain (none available in this environment or the
Docker image).

**J.25–J.27 — Android verification: written, not run.** This is the one
open item left in this thread. Three real test files exist under
`examples/android_consumer/app/src/androidTest/java/com/harpia/android_consumer/`
(commit `7d68c13`) but have never executed — no Android SDK/emulator in
this environment. Task detail:

- [Android-consumption/android-verification-message-classes.md](Android-consumption/android-verification-message-classes.md) (J.25)
- [Android-consumption/android-verification-gRPC-client.md](Android-consumption/android-verification-gRPC-client.md) (J.26)
- [Android-consumption/android-verification-ZMQ-client-track-acceptance-gate.md](Android-consumption/android-verification-ZMQ-client-track-acceptance-gate.md) (J.27)

See [`examples/android_consumer/README.md`](../../../../examples/android_consumer/README.md)
for the full verification-status picture and what running these for
real would need (an Android SDK + emulator).

## Watch for

- The protobuf-runtime-variant decision (full runtime, not `javalite`)
  that these three sessions verify against was made without a real
  Android build available — if J.25–J.27 turn up a DEX-size or
  reflection problem, that decision (not just these tests) may need
  revisiting. See `JavaJsonAdapter/CLAUDE.md` / `JavaXmlAdapter/CLAUDE.md`
  for what depends on the full runtime being reflection-capable.
