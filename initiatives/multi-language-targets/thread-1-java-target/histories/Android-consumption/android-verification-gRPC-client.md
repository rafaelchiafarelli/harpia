
### Session J.26 — Android verification: gRPC client

- **Depends on:** J.24 merged; J.3 (gRPC stubs) merged.
- **Deliverable:** verified on an actual Android build: gRPC client
  (`io.grpc:grpc-android` + `grpc-okhttp`, additive to J.3's stub
  generation, not a replacement).
- **Tests:**
  - Integration: a real Android build making a live gRPC call against a
    generated server.

## Implementation notes (landed 2026-08-23) — written, NOT run

`examples/android_consumer/app/src/androidTest/.../GrpcClientAndroidTest.
java`: constructs a client channel via `io.grpc.android.
AndroidChannelBuilder.usingBuilder(OkHttpChannelBuilder...).context(...)
.build()` and a blocking stub off J.3's generated `users_ServiceGrpc`.
`app/build.gradle` wires `io.grpc:grpc-android`/`grpc-okhttp` (the
Android-specific transport, additive to the stub classes already in the
generated jar), version-pinned to match the desktop/server project's own
`io.grpc:*:1.62.2` (`GradleAdapter/templates/project.gradle.tmpl`) rather
than drifting to a different grpc-java version in the same dependency
graph.

**Not verified against a real device/emulator or a live server** (no
Android SDK here, and no server was stood up to call — this test only
proves the client *constructs*). **Lower confidence than the other two
Android sessions' tests specifically**: the exact
`AndroidChannelBuilder` API shape is reproduced from documentation/memory,
not compiled — see `examples/android_consumer/README.md`'s verification-
status section and this test's own header comment for the full caveat.
