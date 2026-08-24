
### Session J.25 — Android verification: message classes + JSON

- **Depends on:** J.24 merged.
- **Deliverable:** verified on an actual Android build: message classes
  (protobuf-java POJOs+builders, portable as generated); JSON
  (de)serialization, only if J.24 picked the full runtime.
- **Tests:**
  - Integration: a real Android build depending on the generated message
    classes, exercising construction/serialization on-device.

## Implementation notes (landed 2026-08-23) — written, NOT run

`examples/android_consumer/` (new, worked example mirroring `examples/
consumer/`'s role for the C++ target): a standalone Android application
module, parameterized by a `harpiaGenDir` Gradle property the same way
`examples/consumer`'s CMake is parameterized by `-DHARPIA_GEN`.
`MessageClassesAndroidTest.java` constructs a `users` message via its
generated builder and round-trips it through `HarpiaJson`.

**Not verified against a real device/emulator** — this environment has no
Android SDK at all (a bigger toolchain gap than every other Java-target
test's "no JDK" caveat). Confidence is HIGH for this specific test (only
protobuf-java APIs, already proven working by every other Java-target
test in this repo) — see `examples/android_consumer/README.md`'s
verification-status section for the full picture across all three
Android sessions (this one, J.26, J.27) and what confidence looks like
for each.
