### Session J.3 — `protoc --grpc_out` wiring (stub generation)

- **Depends on:** J.2 merged.
- **Deliverable:** gRPC stub generation per J.1's timing — either
  `protoc-gen-grpc-java` invoked at generation time, or the
  `protobuf-gradle-plugin` wiring extended to also run the gRPC plugin.
- **Tests:**
  - Integration: generated gRPC stub compiles and links against J.2's
    message classes.