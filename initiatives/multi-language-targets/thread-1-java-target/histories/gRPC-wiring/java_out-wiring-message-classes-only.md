

### Session J.2 — `protoc --java_out` wiring (message classes only)

- **Depends on:** J.1 merged.
- **Deliverable:** message-class generation per J.1's chosen timing —
  either harpia shells out to `protoc --java_out` at generation time, or
  emits the `build.gradle` wiring for `protobuf-gradle-plugin` to do it.
  No gRPC yet.
- **Out of scope:** gRPC stub generation (J.3).
- **Tests:**
  - Integration: generated Java message classes compile and a
    constructed instance's fields round-trip through the generated
    builder API.