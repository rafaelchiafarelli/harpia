## Hardened links proven on an Android emulator

- **Depends on:** tasks 1, 2, 3.
- **Contract:** `HarpiaTest/app_example/android_consumer` gains instrumented
  tests that make **real network calls from the emulator to C++ servers on the
  host** (reached at `10.0.2.2`). This is the first time an Android client
  talks to a real harpia server.
- **Deliverable:** instrumented tests: (a) gRPC over `grpc-okhttp` +
  `HarpiaGrpcTls` + `HarpiaSession` → C++ `GrpcServer` hardened: `create`
  then `read` a record; (b) JeroMQ SUB with CURVE → C++ PUB with ZAP: receive
  N messages. `Docker/run_android_emulator_tests.sh` extended to start the two
  C++ servers before the emulator tests and stop them after. Server cert SAN
  must include `10.0.2.2` (use epic 3 task 1's `--san` if it has landed,
  otherwise pass it through the existing script's server_CN; pick whichever
  exists, don't build both).
- **Pre-work:** none.
- **Out of scope:** the reference-system app (epic 3).
- **Tests:** the new instrumented tests pass on the emulator; the existing
  4/4 still pass. Watch for ART-only failures like the `ProcessHandle` one
  (e.g. PEM/PKCS8 key parsing, TLS provider differences). Any such failure is
  the real finding: fix it in the runtime and note it in the README.
