## Token-based sessions with expiry / revocation

Scoped 2026-08-30. **Task 5** of the transport-authn epic.

- **Depends on:** task 4 (`rbac`) merged — the RBAC gate and its identity store.
- **Deliverable:** a token-issuance + validation path layered on the RBAC gate.
  A client authenticates once (mTLS client cert → RBAC identity → role) and
  receives a bearer token carrying the role and an expiry; subsequent calls
  present the token instead of re-deriving the identity server-side each time. A
  revocation list is checked on every call. Token format / signing key resolve
  through the F5 `CryptoBackend` seam, not a bespoke choice. Gated by
  `risk_class`.
- **Out of scope:** replacing mTLS (the token rides on top of it, not instead of
  it); the ZAP allowlist; per-field authorization. Reconciling
  `HttpCapabilityAdapter/`'s standalone session mechanism is **optional** — note
  the overlap and do it only if it fits this session's scope, otherwise flag it
  as a follow-up.
- **Tests:**
  - Unit: token expiry (an expired token is rejected), revocation (a revoked
    token is rejected), and the role carried in a token matches the issuing
    identity.
  - Integration: issue a token on one call, use it on the next across REST /
    SOAP / gRPC; expired and revoked tokens both refused with the correct
    status code (401 / UNAUTHENTICATED).
  - Golden: regenerated, diff reviewed.
- **Doc-comments:** template + bring-up-glue doc-comments describing the session
  flow (obtain token, present token, expiry / revocation).

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
