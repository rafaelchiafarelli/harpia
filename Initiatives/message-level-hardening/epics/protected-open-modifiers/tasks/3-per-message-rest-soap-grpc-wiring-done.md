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

## Implementation note

Two design questions surfaced only once the call graph was traced, and were
resolved with Rafael before landing (not silently inferred):

- **No composition propagation.** A message's own `is_protected`/`is_open`
  is the *only* input to its own gate. Composing an `open` message inside a
  `protected` one does not force it protected (and the reverse can't
  conflict either) — a deliberate simplicity choice: "if a message is
  protected, it is protected; if it is not, it is not." Losing the
  protection this way is the schema author's call, not something harpia
  infers or blocks; a discouragement log for this case, and any actual
  per-version propagation tooling, are explicitly deferred to a future task,
  not built here.
- **Transport promotion.** A `protected` message in an otherwise-unhardened
  project (or an `open` message in an otherwise-hardened one) promotes that
  *project's* REST/SOAP/gRPC bring-up to the shape it needs (TLS-capable,
  client-cert requested-not-required per task 2's confirmed approach) —
  `Database/auth_gate.py`'s `transport_mode()`. This never touches a project
  where no message's `effective_rbac()` diverges from the project-wide
  default, which is what keeps a project using neither modifier anywhere
  byte-identical (`UnitTests/test_golden.py`/`test_golden_java.py`
  unaffected; the only golden drift from this task is in the two hand-written
  runtime headers' own doc comments and new optional parameter,
  `harpia_http_mtls.h` / `harpia_grpc_mtls.h`, which ship verbatim into every
  generated project).

Landed in `Database/auth_gate.py` (`effective_rbac()`, `transport_mode()`),
`RestAdapter.py`/`SoapAdapter.py`/`GrpcServiceAdapter.py` (per-message gate +
mixed-mode bring-up), `Database/runtime/harpia_{http,grpc}_mtls.h` (new
optional `client_cert_required` param, default `true`), and the two bring-up
templates (new fills, all no-ops in the byte-identical case). Tests:
`UnitTests/test_message_hardening_gate.py`.
