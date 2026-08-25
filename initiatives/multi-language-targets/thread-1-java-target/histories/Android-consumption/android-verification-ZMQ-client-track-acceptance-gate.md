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

**Track acceptance gate status (updated 2026-08-24): compiles for real,
still not met.** This session's own bar — "the Android consumption path
was verified for real" — requires an actual device/emulator run of all
three `examples/android_consumer` tests. The harpia Docker image
([`../../../../../Dockerfile`](../../../../../Dockerfile)) now carries a
JDK 17 + Gradle 8.5 + Android SDK (cmdline-tools, platform-tools,
`platforms;android-34`, `build-tools;34.0.0`), and against that real
toolchain: all three tests compile clean
(`assembleDebugAndroidTest`), and `assembleRelease` with R8 succeeds with
multidex activating cleanly (~105,822 total methods across two dex
files) — confirming J.24's protobuf-runtime decision for real. Two real
bugs (an illegal `--` inside an XML comment in `AndroidManifest.xml`, and
a missing `gradle.properties` needed for `android.useAndroidX=true`) were
found and fixed by this compile pass — exactly the kind of thing "written
but never compiled" code has.

**What's still not done:** no Android SDK emulator or physical device was
available (Docker itself works now, but an emulator inside a container
needs `/dev/kvm` passed through, which needs nested virtualization enabled
up the host chain — untested). So the actual `connectedAndroidTest` runs
— the one thing this session's acceptance gate actually requires — still
haven't happened. That remains the literal remaining item to close this
track out; see `examples/android_consumer/README.md`'s verification-status
section for the current, precise split between what's compile-verified
and what isn't.