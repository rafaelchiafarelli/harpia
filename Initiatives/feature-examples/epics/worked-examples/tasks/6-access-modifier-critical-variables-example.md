## Access-modifier ("critical variables") example

- **Depends on:** task 1, task 2 (reuses its gRPC server for the gRPC half).
- **Deliverable:** `HarpiaTest/app_example/access_demo/` — credential-gated access over
  REST (and gRPC) showing correct vs. wrong `X-User`/`X-Pswd` →
  200 vs 401/`UNAUTHENTICATED`, `users` message. README states explicitly
  this is the closest existing analog to "critical variables" and links
  `Initiatives/medical_devices/harpia_sensitive_data_design_rules.md` for
  the real (unimplemented) `critical` concept, so nobody mistakes this
  demo for that future feature.
- **Tests:** build + run inside `Docker/run.sh`; both the accept and
  reject paths actually exercised, not just the happy path.

