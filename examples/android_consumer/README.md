# Consuming Harpia's Java target on Android — worked example (unverified)

A **standalone Android application module** that uses harpia's Java-target
output as a black box — the Android-side counterpart to
[`examples/consumer`](../consumer) (the C++ target's worked example). It
does not depend on the harpia repo — only on a project you generate with
`HARPIA_GEN_LANG=java`, pointed at via the `harpiaGenDir` Gradle property.

It exercises, for the `users`/`courier` messages
([`HarpiaTest/test.harpia`](../../HarpiaTest/test.harpia)), the three
things [thread-1-java-target README.md §7](../../initiatives/multi-language-targets/thread-1-java-target/README.md#7-android-consumption--the-actual-motivating-use-case)
identifies as the actual Android consumption surface:
- **message classes + JSON** (`MessageClassesAndroidTest`, session J.25),
- **gRPC client** (`GrpcClientAndroidTest`, session J.26),
- **ZMQ client** (`ZmqClientAndroidTest`, session J.27) — the one piece
  this thread's own docs flag as genuinely unconfirmed on-device
  specifically, since JeroMQ is pure Java but had never been checked
  against Android's ART runtime before this.

## ⚠️ Verification status: written, not run

**Every file in this module was written without any Android SDK, AVD
emulator, or connected device available in the environment that wrote
it.** That's a strictly bigger toolchain gap than every other Java-target
integration test in this repo carries (those need "just" a JDK + Gradle,
both plausibly addable to the harpia Docker image; a full Android
verification needs the Android SDK/build-tools *and* either an emulator
with hardware virtualization or a physical device — neither is available
in a typical sandboxed CI/agent environment).

Concretely, that means:
- The `android.` Gradle config, dependency versions, and
  `io.grpc.android.AndroidChannelBuilder` API usage are reproduced from
  documentation and prior knowledge, not compiled against real Android
  build-tools. Confidence is HIGH for the message-class/JSON (J.25) and
  ZMQ (J.27) tests (they only touch protobuf-java/JeroMQ APIs already
  exercised successfully by this repo's JDK-gated tests elsewhere), LOWER
  for `GrpcClientAndroidTest` (J.26) specifically — see its own header
  comment.
- Android Gradle Plugin is pinned to **8.2.2** (not the actual latest,
  AGP 9.3 / compileSdk 37, as of a 2026-08-23 web check) — deliberately,
  because this module was written with much higher confidence in AGP
  8.x's exact config surface than 9.x's. Bump this once it's actually
  built against real tooling, not by drift.
- **None of `MessageClassesAndroidTest`/`GrpcClientAndroidTest`/
  `ZmqClientAndroidTest` have ever run.** They're written to the same
  "correct by inspection, verified for real once the toolchain exists"
  standard as every gradle+JDK-gated test elsewhere in this repo's
  `tests/test_java_*.py` — just one rung further out on what's missing to
  actually run them.

If you're picking this up with real Android tooling available: run it,
fix what's wrong, and update this section (and the three session history
files under
[`../../initiatives/multi-language-targets/thread-1-java-target/histories/Android-consumption/`](../../initiatives/multi-language-targets/thread-1-java-target/histories/Android-consumption/))
to say so — don't let this warning go stale once it's no longer true.

## Run it (once Android tooling is available)

```sh
# 1. generate a Java-target project from a .harpia (the bundled HarpiaTest)
HARPIA_GEN_LANG=java HARPIA_OUTPUT_DIR=/tmp/gen python3 main.py

# 2. build the generated project's own jar (message classes, gRPC stubs,
#    every Java-target runtime class) -- this module depends on it.
(cd /tmp/gen/java && gradle build)

# 3. build + run this module's instrumented tests against a connected
#    device or a running emulator (`adb devices` must show one)
./gradlew connectedAndroidTest -PharpiaGenDir=/tmp/gen
```

For J.26's gRPC test specifically, a generated server needs to be running
on the HOST machine (the emulator reaches it via the `10.0.2.2` loopback
alias baked into the test) — e.g. the C++ target's own generated gRPC
server, or a Java-target one once REST/SOAP/gRPC-service-impl gain
server-side Android... except they don't: per J.27's own scope, DB/REST/
SOAP servers and the gRPC service impl are **never** consumed on-device
(a phone isn't meant to host these) — the server side always runs
elsewhere.

## Files
- [`app/build.gradle`](app/build.gradle) — how the generated project's
  jar and the Android-specific runtime deps (grpc-android/grpc-okhttp,
  jeromq, protobuf-java) are wired in, parameterized by `harpiaGenDir`.
- [`app/src/androidTest/`](app/src/androidTest/java/com/harpia/android_consumer/) —
  the three instrumented tests (J.25/J.26/J.27), one per Android
  consumption surface.

## Notes
- Generated class names are plain (not hash-qualified, unlike C++ header
  filenames) — `option java_multiple_files`/`java_package` land every
  message/service class in the flat `com.harpia.generated` package (see
  `protoFile/CLAUDE.md`'s `JAVA_PACKAGE` note, including its flagged
  multi-root collision risk). This example is pinned to
  `HarpiaTest/test.harpia`'s `users`/`courier` messages; regenerate from
  your own input and the class names carry over unchanged (same package,
  different message names) as long as they don't collide with another
  root's.
