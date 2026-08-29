## Capability-negotiation example

- **Depends on:** task 1.
- **Deliverable:** `HarpiaTest/app_example/capability_demo/` — gRPC capability
  negotiation: a real `harpia::capability::negotiate()` call against a
  server with `capabilities_service` registered, and again against a stub
  server that doesn't (legacy-peer fallback), printing both outcomes.
- **Tests:** build + run inside `Docker/run.sh`; both outcomes (real
  negotiation, legacy-peer fallback) actually observed in program output.

