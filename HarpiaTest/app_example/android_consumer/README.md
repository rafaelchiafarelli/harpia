# Consuming Harpia's Java target on Android — worked example (device-verified)

A **standalone Android application module** that uses harpia's Java-target
output as a black box — the Android-side counterpart to
[`HarpiaTest/app_example/consumer`](../consumer) (the C++ target's worked example). It
does not depend on the harpia repo — only on a project you generate with
`HARPIA_GEN_LANG=java`, pointed at via the `harpiaGenDir` Gradle property.

## Why this is a *consumer*, not a second build target

The Java target's full output is a standard JVM server/library project —
the same relationship the C++ target's output has to a native server, not
something that runs on-device as-is. An Android app only ever consumes a
*subset* of it — this module exists to prove that subset works for real,
not to add Android as a separate generation target with its own adapters:

- **Message classes** (protobuf-java POJOs+builders) — fully portable,
  pure Java, no JNI, no reason this doesn't work on Android as generated.
- **JSON (de)serialization** — portable *if and only if* the full
  protobuf runtime (not `protobuf-javalite`) is what got generated — see
  [`JavaJsonAdapter/CLAUDE.md`](../../../JavaJsonAdapter/CLAUDE.md) for the
  full runtime-variant decision and why it matters specifically for
  Android.
- **gRPC client** — `io.grpc:grpc-android` + `grpc-okhttp`, the
  Android-specific transport, additive to the generated stub classes
  (full `grpc-netty` is a desktop/server thing).
- **ZMQ client (JeroMQ)** — pure Java, no JNI; the one piece that needed
  an actual on-device run to confirm (see Verification status below),
  since a pure-Java ZMTP reimplementation running on ART was a genuinely
  open question, not settled Android practice the way message
  classes/JSON/gRPC already are.
- **DB/CRUDL, REST/SOAP servers, gRPC service impl — never consumed
  on-device.** `com.sun.net.httpserver` and JDBC drivers are
  desktop/server-JVM assumptions, and a phone isn't meant to host a
  server anyway — out of scope for this module regardless of whether
  they'd even work on Android's API surface.

It exercises this surface, for the `users`/`courier` messages
([`HarpiaTest/test.harpia`](../../test.harpia)), across three
instrumented test classes:
- **message classes + JSON** (`MessageClassesAndroidTest`),
- **gRPC client** (`GrpcClientAndroidTest`),
- **ZMQ client** (`ZmqClientAndroidTest`).

## ✅ Verification status (updated 2026-08-25)

**Verified for real, on-device.** `docker/run_android_emulator_tests.sh`
boots a headless Android emulator (hardware-accelerated via `/dev/kvm`)
and runs all three instrumented tests against it. Latest run:
`grpcAndroidClientConstructsAgainstGeneratedStub`,
`jsonRoundTripWorksOnDevice`, `messageClassConstructsAndReadsBackOnDevice`,
`pushPullRoundTripWorksOnDevice` — **4/4 passed** (`emulator-5554`, 0
failures, 0 errors, 2026-08-25T23:11:34,
`app/build/outputs/androidTest-results/connected/debug/`).

This run found one real bug — the actual value of verifying on-device
instead of stopping at "compiles clean": `HarpiaZmq.runtimeOriginId()`
(`JavaZmqAdapter/runtime/HarpiaZmq.java`) called `java.lang.ProcessHandle`,
a JDK9+ API Android's ART runtime doesn't implement — invisible to any
compile-time check (the desktop JDK compiling it has the class), only
surfacing when the code actually runs on ART.
`ZmqClientAndroidTest.pushPullRoundTripWorksOnDevice` failed with
`NoClassDefFoundError` until fixed: the pid component of the
sender-uniqueness id was replaced with a `SecureRandom` value generated
once per JVM/process instance — portable across desktop JVM and ART, and
arguably a stronger uniqueness guarantee than a real OS pid (which gets
reused over a long-running host's lifetime; this never does).

Three more bugs, all in the emulator/Docker infrastructure itself (not
generated code), were fixed to get this running at all: the `emulator`
binary's own directory wasn't on the Dockerfile's `PATH`; `avdmanager
create avd` ignores `ANDROID_AVD_HOME` and instead resolves its write
target through Java's `user.home`, which `getpwuid` resolves to the
image's baked-in `/home/ubuntu` regardless of the `HOME` env var (the same
class of gotcha the Dockerfile already documents for Gradle's
`GRADLE_USER_HOME`) — fixed by forcing `-Duser.home=/tmp` via `JAVA_OPTS`;
and the interactive hardware-profile prompt was flaky under non-TTY stdin,
fixed by passing `-d pixel_5` so `avdmanager` doesn't prompt at all.

### Older, compile-only pass (2026-08-24) — superseded by the above

**Compiles for real now — the harpia Docker image ([`../../../Dockerfile`](../../../Dockerfile))
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

This 2026-08-24 pass didn't have `/dev/kvm` wired in yet, so none of the
three `connectedAndroidTest` runs had actually executed on-device —
resolved by the 2026-08-25 pass above.

## Run it

```sh
# 1. generate a Java-target project from a .harpia (the bundled HarpiaTest)
HARPIA_GEN_LANG=java HARPIA_OUTPUT_DIR=/tmp/gen python3 main.py

# 2. build the generated project's own jar (message classes, gRPC stubs,
#    every Java-target runtime class) -- this module depends on it.
(cd /tmp/gen/java && gradle --no-daemon build)

# 2b. compile-only sanity check, no device needed:
gradle --no-daemon -PharpiaGenDir=/tmp/gen assembleDebugAndroidTest
gradle --no-daemon -PharpiaGenDir=/tmp/gen assembleRelease   # R8/DEX check

# 3. build + run this module's instrumented tests against a connected
#    device or a running emulator (`adb devices` must show one).
gradle --no-daemon connectedAndroidTest -PharpiaGenDir=/tmp/gen
```

Steps 1-3 all work inside the harpia Docker image. For step 3 specifically
— which needs a device/emulator, not just the SDK — use
[`docker/run_android_emulator_tests.sh`](../../../docker/run_android_emulator_tests.sh)
instead of `docker/run.sh`: it boots a headless, hardware-accelerated
(`/dev/kvm`) emulator inside the container and runs steps 1-3 against it
end to end. Requires `/dev/kvm` on the host (nested virtualization enabled,
if the host itself is a VM).

`GrpcClientAndroidTest` only constructs the client and asserts the stub is
non-null — it doesn't make a live RPC call, so no server needs to be
running to pass it. A real end-to-end call (against a generated server on
the host, reachable from the emulator via the `10.0.2.2` loopback alias)
is out of scope for this test and hasn't been exercised.

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
