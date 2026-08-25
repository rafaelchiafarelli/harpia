### Session J.24 — Protobuf runtime variant decision

- **Depends on:** J.4 (JSON), J.10/J.11 (XML) merged — the decision needs
  to weigh what those two would lose under `javalite`.
- **Decide for real, against an actual Android build, not a guess
  (`../../README.md` §4 item 2):** full runtime (reflection-capable,
  required by J.4's `JsonFormat` and J.10/J.11's XML runtime) vs.
  `protobuf-javalite` (Android-oriented, DEX-friendly, not reflection-
  capable — loses JSON/XML for free if picked). This is the fork between
  "full symmetric target" and "what Android apps actually reach for."
- **Deliverable:** a documented decision plus the Gradle module
  configuration reflecting it, ready for J.25–J.27 to build against.
- **Tests:** none — this is a decision-and-configuration session.

## Decision (2026-08-23): full protobuf-java runtime, not `protobuf-javalite`

**Not verified against a real Android build**, unlike this session's own
instruction — flagged plainly, not glossed over: this sandbox has no
Android SDK/build-tools/emulator at all (a strictly bigger toolchain gap
than the "no JDK" caveat every other Java integration test in this thread
has already carried — Android verification needs the SDK *and* either an
emulator with hardware virtualization or a connected device, neither
obtainable here). This is a reasoned engineering call, not a guess, but
it is exactly the kind of call this session was supposed to make *for
real* against a build — see "What would actually confirm this" below for
what J.25 needs to check first.

**Reasoning:**
1. Per `../../README.md` §7, Android consumption is scoped to message
   classes + JSON + gRPC client + ZMQ client — XML/REST/SOAP/DB are never
   consumed on-device at all (J.27's own "Out of scope" line). So this
   decision is really only about **JSON** (J.4's `HarpiaJson`, built on
   `JsonFormat`, itself built on full-runtime reflection) — XML doesn't
   even enter into what Android needs, despite also depending on the full
   runtime.
2. J.4 already shipped and tested `HarpiaJson` against the full runtime.
   Switching to `protobuf-javalite` now wouldn't just be a config flag —
   `javalite`-generated classes have no `getDescriptorForType()`/
   reflection API at all, so `HarpiaJson` (and `JdbcBind`, and every other
   reflection-based Java-target runtime this thread built) would need a
   **second, non-reflective implementation** specifically for Android, a
   real and ongoing maintenance cost, not a one-time swap.
3. The DEX-method-count pressure that originally motivated `javalite`
   (mid-2010s Android) is substantially mitigated by tooling that's now
   standard: multidex has shipped since API 21 (2014), and R8 full-mode
   shrinking in release builds aggressively strips unused code. The
   argument for `javalite` is weaker in 2026 than when it was designed,
   though not zero.
4. `io.grpc:grpc-android`/`grpc-okhttp` (J.26) already carry a non-trivial
   method-count footprint of their own, regardless of the protobuf
   runtime choice — reducing how much of the *overall* app's DEX pressure
   the javalite-vs-full choice actually controls.
5. The concrete motivating use case (`../../README.md`'s own framing: an
   existing Android fleet wanting harpia-generated Java code *now*) is
   documented as wanting parity with the full target, not a hand-picked
   minimal subset — nothing in this thread's history names DEX size as an
   actual constraint that fleet has hit.

**Gradle configuration implication:** none needed as a *change* —
`GradleAdapter/templates/project.gradle.tmpl` already depends on
`com.google.protobuf:protobuf-java` (full runtime), not a lite variant,
since J.2. This decision confirms that choice extends to the Android
consumption path too, rather than introducing a second, Android-specific
protobuf runtime.

**What would actually confirm this** (J.25's real job, not just message-
class verification): build a small Android app module depending on the
generated `java/` module's message classes + `HarpiaJson`, run
`./gradlew assembleRelease` with R8 enabled, and check the resulting
APK's method count / DEX file count against the 64K single-dex limit (or
confirm multidex activates cleanly). If that build hits real trouble
`javalite` would have avoided, THIS decision is the one to revisit — not
silently work around downstream.

## Confirmed against a real build (2026-08-24)

The harpia Docker image gained a JDK 17 + Gradle 8.5 + Android SDK
toolchain, and `examples/android_consumer`'s `assembleRelease` (R8
enabled) was actually run against it. Result: `classes.dex` =
63,062 methods, `classes2.dex` = 42,760 methods (~105,822 total, read
directly from each dex header's `method_ids_size`) — over the 65,536
single-dex limit, so multidex genuinely activates, and does so cleanly
with no build failure. This is exactly the "confirm multidex activates
cleanly" outcome above; the full-runtime decision stands, confirmed rather
than reasoned. Still not run: any of the three `connectedAndroidTest`s
(no device/emulator available) — see `examples/android_consumer/README.md`
for the current split between what's compile-verified and what isn't.
