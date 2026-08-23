
### Session J.26 — Android verification: gRPC client

- **Depends on:** J.24 merged; J.3 (gRPC stubs) merged.
- **Deliverable:** verified on an actual Android build: gRPC client
  (`io.grpc:grpc-android` + `grpc-okhttp`, additive to J.3's stub
  generation, not a replacement).
- **Tests:**
  - Integration: a real Android build making a live gRPC call against a
    generated server.
