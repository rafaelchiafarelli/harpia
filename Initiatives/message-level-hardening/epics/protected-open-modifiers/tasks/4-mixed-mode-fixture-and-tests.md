## Mixed-mode proof: one project, both gated and open messages, all three transports

- **Depends on:** task 3.
- **Deliverable:** two small fixtures under `HarpiaTest/Include/` (not
  `test.harpia`):
  - A hardened project (`risk_class: class_c` or `topology:
    cloud_connected`) containing at least one table-bearing message with the
    `open` modifier. Assert its REST/SOAP/gRPC CRUD endpoints serve an
    anonymous caller successfully, while every other message in the same
    project still enforces the RBAC/session gate as today.
  - An unhardened project (no compliance profile, or a profile that
    resolves `transport_hardening_required()` to `False`) containing at
    least one table-bearing message with the `protected` modifier. Assert
    its endpoints refuse an anonymous caller (401/`UNAUTHENTICATED`) while
    every other message in the same project stays on the flat
    `X-User`/`X-Pswd`-style credential unchanged.
  - Both fixtures built and run against a live server in-process (same
    pattern as `UnitTests/test_rest_soap_mtls.py`/`test_grpc_mtls.py`), not
    just a unit-level check of the generated source text.
- **Out of scope:** performance, load, anything beyond proving the two mixed
  scenarios above function correctly.
- **Verification:** full suite green in Docker
  (`Docker/run.sh pytest UnitTests/`), including these new tests.
