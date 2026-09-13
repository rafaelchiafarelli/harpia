## Per-message RBAC/session gating for REST, SOAP, and gRPC

- **Depends on:** task 1 (`is_protected`/`is_open` flags exist), task 2 (a
  confirmed, written approach for serving mixed gated/anonymous routes from
  one server — this task implements that approach, it does not invent its
  own).
- **Deliverable:** `Database/auth_gate.py` and its three callers
  (`RestAdapter.py`, `SoapAdapter.py`, `GrpcServiceAdapter.py`) compute the
  gate **per message** instead of once per project:
  `effective_rbac = msg.is_protected or (transport_hardening_required(compliance) and not msg.is_open)`.
  Replace each adapter's single `rbac = transport_hardening_required(...)`
  computed before the message loop with this per-message expression inside
  the loop, threaded into `rest_auth_fills`/`soap_auth_fills`/
  `grpc_auth_fills` unchanged otherwise (they already take `rbac` as a
  parameter — no signature change needed, just a different value per call).
  Server-level TLS/mTLS setup itself changes per task 2's finding (e.g.
  client-cert-requested-not-required when the project has at least one
  `open` message alongside a hardened default, or at least one `protected`
  message alongside an open default — a genuinely mixed project).
- **Out of scope:** ZMQ, DDS (deferred epic). Any change to
  `harpia::rbac::decide`'s own logic, `HARPIA_RBAC_MAP`, or session
  token issuance/verification — this task only changes which messages the
  existing gate applies to.
- **Tests:** unit-level — for a hardened project, an `open` message's
  endpoints (REST/SOAP/gRPC) serve an anonymous request with no 401/403; for
  an unhardened project, a `protected` message's endpoints refuse an
  anonymous request the same way today's hardened-project flat gate does.
  Reuse `UnitTests/test_rbac.py`'s existing harness pattern rather than
  building a new one.
