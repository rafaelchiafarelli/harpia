## mTLS on REST/SOAP

Scoped 2026-08-30. **Task 3** of the transport-authn epic. REST and SOAP
together, not two efforts — they already share one `crow::SimpleApp`
(`register_{name}` / `register_{name}_soap` both take `crow::SimpleApp&`), the
same reasoning that produced `HttpCapabilityAdapter/` as one mechanism rather
than two. No dependency on task 2.

- **Depends on:** task 1 (`cert-provisioning`) merged; F1, F3 (Foundation).
- **Deliverable:** the generated server bring-up glue configures the shared
  `crow::SimpleApp` for TLS with client-cert verification required when
  `transport_hardening_required(compliance)` is true; plaintext HTTP refused in
  that mode. Cert / key / CA from task 1's `USE_MTLS` build-flag convention. The
  `authorized_{name}()` header check and the SOAP `<credentials>` check are
  untouched by this task — mTLS sits under them.
- **Guarantees:** with hardening on, REST and SOAP requests with no client cert
  are refused at the TLS handshake; requests with a valid task-1 client cert
  proceed to the existing `authorized_{name}` / `<credentials>` gate. With
  hardening off, behaviour is what it is today.
- **Out of scope:** RBAC (task 4); gRPC (task 2); sessions (task 5); reconciling
  the `HttpCapabilityAdapter/` standalone path (task 5's optional concern).
- **Tests:**
  - Integration (`UnitTests/test_stage11_soap.py`, `test_stage12_rest.py`):
    live REST and SOAP calls over TLS with client certs — refused without,
    accepted with, under hardening = true; unchanged plaintext when false.
  - Golden: regenerated, diff reviewed — server bring-up glue moves; the route
    helper templates (`rest.h.tmpl` / `soap.h.tmpl` bodies) should not — verify.
- **Doc-comments:** `rest.h.tmpl` / `soap.h.tmpl` header blocks + the bring-up
  glue updated for the TLS mode.
- **Watch for:** crow's built-in `.ssl_file()` does server-side TLS only.
  Requiring *and verifying* a client cert needs a custom
  `boost::asio::ssl::context` with `verify_peer | verify_fail_if_no_peer_cert`
  handed to the app. If that fights crow's public API badly enough to need a
  vendored patch or a transport rewrite, that is a signal to stop and re-scope
  with Rafael, not to patch around it.

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
