# Consuming Harpia's Java target on Android — worked example (compile-verified, not device-verified)

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

## ⚠️ Verification status (updated 2026-08-24)

**Compiles for real now — the harpia Docker image ([`../../Dockerfile`](../../Dockerfile))
gained a JDK 17 + Gradle 8.5 + Android SDK (cmdline-tools, platform-tools,
`platforms;android-34`, `build-tools;34.0.0`) toolchain.** Against that
real toolchain:
- `gradle -PharpiaGenDir=... assembleDebugAndroidTest` **compiles all
  three** instrumented tests (`MessageClassesAndroidTest`,
  `GrpcClientAndroidTest`, `ZmqClientAndroidTest`) successfully — the code
  itself was sound.
- `gradle -PharpiaGenDir=... assembleRelease` (R8 enabled) **succeeds**,
  and the resulting APK's dex files were checked directly (dex header
  `method_ids_size`): `classes.dex` = 63,062 methods, `classes2.dex` =
  42,760 methods, ~105,822 total — over the 65,536 single-dex limit, so
  **multidex genuinely activates, and does so cleanly**, exactly the check
  `protobuf-runtime-variant-decision.md` (J.24) called for. That decision
  (full `protobuf-java` runtime over `protobuf-javalite`) is now confirmed
  against a real build, not just reasoned.
- Two real bugs surfaced and were fixed by this compile pass, both the
  kind only a real build catches: `app/src/main/AndroidManifest.xml`'s
  header comment used `--` inside an XML comment (illegal — `--` may only
  appear as the closing delimiter), and `gradle.properties` didn't exist
  at all, so AGP refused to resolve the AndroidX test dependencies
  (`android.useAndroidX=true` is required even though this module has no
  other AndroidX-dependent code). Both fixed in place. (One suspected
  third bug — `implementation` vs `androidTestImplementation` scoping for
  the harpia jar/protobuf/gRPC/jeromq deps — turned out to be a false
  alarm from a flawed test harness losing the generated project between
  container runs, not a real issue; the original `implementation` scoping
  is correct and unchanged.)
- Android Gradle Plugin is still pinned to **8.2.2** (not the actual
  latest, AGP 9.3 / compileSdk 37, as of a 2026-08-23 web check) —
  deliberately; now confirmed to actually work at this pin, not just
  plausible.

**Still not verified:** no emulator or physical device was available in
the environment that ran this (Docker itself is reachable now, but an
Android emulator inside a container needs `/dev/kvm` passed through, which
needs nested virtualization enabled up the host chain — untested here).
So **none of the three `connectedAndroidTest` runs have actually executed
on-device.** `GrpcClientAndroidTest`'s `AndroidChannelBuilder` usage in
particular compiles clean but is still unconfirmed to behave correctly at
runtime against a live gRPC server. That's the one gap this pass didn't
close — see the three session history files under
[`../../initiatives/multi-language-targets/thread-1-java-target/histories/Android-consumption/`](../../initiatives/multi-language-targets/thread-1-java-target/histories/Android-consumption/)
for what running those for real still needs.

## Run it

Steps 1-2 (and compiling this module, steps below) now work inside the
harpia Docker image (`docker/run.sh`), which carries a JDK 17 + Gradle 8.5
+ Android SDK toolchain. Step 3 still needs a connected device or emulator
reachable from wherever you run it — not provided by the image itself.

```sh
# 1. generate a Java-target project from a .harpia (the bundled HarpiaTest)
HARPIA_GEN_LANG=java HARPIA_OUTPUT_DIR=/tmp/gen python3 main.py

# 2. build the generated project's own jar (message classes, gRPC stubs,
#    every Java-target runtime class) -- this module depends on it.
(cd /tmp/gen/java && gradle --no-daemon build)

# 2b. compile-only sanity check, no device needed (confirmed working):
gradle --no-daemon -PharpiaGenDir=/tmp/gen assembleDebugAndroidTest
gradle --no-daemon -PharpiaGenDir=/tmp/gen assembleRelease   # R8/DEX check

# 3. build + run this module's instrumented tests against a connected
#    device or a running emulator (`adb devices` must show one) --
#    NOT YET DONE, no device/emulator available in the environment
#    that verified steps 1-2b.
gradle --no-daemon connectedAndroidTest -PharpiaGenDir=/tmp/gen
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
