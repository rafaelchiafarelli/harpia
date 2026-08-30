## mTLS on gRPC

Scoped 2026-08-30. **Task 2** of the transport-authn epic. No dependency on
task 3 — the two mTLS tasks may run in parallel on separate session-lines.

- **Depends on:** task 1 (`cert-provisioning`) merged; F1, F3 (Foundation).
- **Deliverable:** the generated gRPC server (`grpc::ServerBuilder` in the
  bring-up glue) uses `grpc::SslServerCredentials` with client-cert verification
  required (`GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY`) when
  `transport_hardening_required(compliance)` is true; `InsecureServerCredentials`
  is refused in that mode. The generated client stub builds channel credentials
  from a task-1 client cert. Cert / key / CA paths follow the `USE_MTLS`
  build-flag convention task 1 established.
- **Guarantees:** with hardening on, a gRPC call with no client cert fails at
  the TLS handshake (UNAVAILABLE), a call with a valid task-1 client cert
  connects; the existing credential-metadata check (`authorized()` in
  `grpc_service.h.tmpl`) still runs on top, unchanged by this task. With
  hardening off, behaviour is byte-for-byte what it is today.
- **Out of scope:** replacing the credential-metadata gate with RBAC (task 4);
  REST / SOAP (task 3); sessions (task 5).
- **Tests:**
  - Integration (`UnitTests/test_*grpc*` shape): live gRPC call over TLS with
    client certs — refused with no cert, accepted with a valid task-1 cert,
    under `transport_hardening_required` = true; unchanged plaintext path when
    false.
  - Golden: `test_golden.py` (+ `_java`) regenerated, diff reviewed — the
    server-bring-up glue and any TLS scaffolding move; the `.proto` and service
    method signatures must not.
- **Doc-comments:** `grpc_service.h.tmpl`'s header block + the bring-up glue
  updated to describe the TLS mode and how `transport_hardening_required` gates
  it.
- **Watch for:** the credential-metadata `authorized()` check and the TLS layer
  are independent — this task adds the second without touching the first. If
  wiring `SslServerCredentials` into the generated `ServerBuilder` glue turns
  out to need a bring-up-glue refactor bigger than one session, that is a signal
  to split the glue rework into its own task, not to inline it here.

---
## Epic context — transport-authn

**Contract.** mTLS on all three HTTP-family transports (gRPC / REST / SOAP),
admin/main/guest RBAC replacing the flat `X-User`/`X-Pswd` gate, token-based
sessions with expiry/revocation, and cert provisioning scripts — plus a ZMQ
CURVE ZAP client-key allowlist (absorbed from zmq-lifecycle 2026-08-29). One
implementation per project, compiled in and gated by `risk_class`, never
per-jurisdiction (`harpia_medical_master_plan.md` §0a). Needs `ComplianceContext`
(F1), the `AuditSink` stub (F3), and the `CryptoBackend` seam (F5) from
Foundation — the TLS stack links the F5 seam's `transport_security()` /
`transport_hardening_required()`, it does not pick its own crypto module.

**Files.** `Assets/` (cert provisioning scripts + `CMakeLists.txt` / `vcpkg.json`
wiring); `Database/templates/{rest,soap,grpc_service}.h.tmpl` and their emitters
`Database/{RestAdapter,SoapAdapter,GrpcServiceAdapter}.py` (the credential gate —
`authorized_{name}()` helper + the 401 / UNAUTHENTICATED check at each route);
the generated server bring-up glue that instantiates `crow::SimpleApp` /
`grpc::ServerBuilder` (`Assets/server_template/`, `main.py` glue) for the TLS
listener config; `ZmqAdapter/` for the absorbed ZAP-allowlist work.

**Ordering (within the epic).** cert-provisioning → mTLS (gRPC ∥ REST/SOAP) →
RBAC → sessions → acceptance-gate note. Auth sits on top of an authenticated
transport, not the other way around. mtls-grpc and mtls-rest-soap have no
dependency on each other and may run on two session-lines; do not reorder them
ahead of cert-provisioning or after RBAC.

**Not scoped as a task yet.** The ZMQ CURVE ZAP allowlist stays a documented
deliverable, not a numbered task, until task 4's identity store is real — the
allowlist must read from *that* store, not invent its own
(`transport-authn/README.md`, "Watch for"). Scope it after task 4. The
`HttpCapabilityAdapter/` session mechanism (a standalone REST/SOAP path shipped
by the message-versioning effort) is an opportunity to reconcile with task 5's
real session model, not an obligation.

**Decision to confirm (provisioning posture).** Task 1 is scoped as a local
CA + leaf-issuance tool (root CA, server cert, per-identity client certs with
subject CN = the RBAC principal) in dev/bootstrap posture — real enough to be
the identity source RBAC (task 4) and the ZAP allowlist build on, but not an
integration with an external enterprise CA / HSM (that stays a pluggable
follow-up, same boundary `KeyProvider` keeps). Flagged for Rafael; revisit
task 1's scope if that reading is wrong.
