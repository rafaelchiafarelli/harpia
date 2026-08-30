## RBAC (admin / main / guest)

Scoped 2026-08-30. **Task 4** of the transport-authn epic. Replaces the flat
`X-User`/`X-Pswd` (REST), `<credentials>` (SOAP) and credential-metadata (gRPC)
gate with a three-role model across all three transports. **This task's identity
store is what the ZAP-allowlist deliverable and task 5's sessions read from** —
its shape gets pinned here, during implementation, not left implicit.

- **Depends on:** tasks 2 (`mtls-grpc`) and 3 (`mtls-rest-soap`) merged — a role
  check sits on top of an authenticated transport. F1, F3 (Foundation).
- **Deliverable:**
  - a role model `admin` / `main` / `guest` and a role × operation permission
    matrix (which of push / pullByID / pullByFilter / stream / heartBeat each
    role may call), gated by `risk_class` — one matrix per project, never
    per-jurisdiction (§0a);
  - the identity → role binding, keyed on the task-1 client-cert subject CN.
    **Pin the store shape in this file when implementing** — a generated
    compiled-in map, or a config file read at startup; do not leave it as an
    inferred choice;
  - the generated gate (`authorized_{name}` and the SOAP / gRPC equivalents)
    replaced by a role check emitting differentiated **401** (no / unverifiable
    identity) vs **403** (valid identity, wrong role); UNAUTHENTICATED vs
    PERMISSION_DENIED for gRPC;
  - one `AuditSink` record per **denied** access — operation, identity, role,
    decision; never a credential value (design-rules Rule 5).
- **Out of scope:** token sessions (task 5); the ZAP allowlist (scope it as its
  own task after this one); per-field authorization (not in this epic);
  provisioning identities (task 1).
- **Tests:**
  - Unit: the full role × operation matrix as an allow/deny table.
  - Integration: live gRPC / REST / SOAP calls — 401 with no cert, 403 with a
    valid cert bound to the wrong role, 200 with the correct role, on each
    transport.
  - Unit: exactly one `AuditSink` record per denial, names only in `detail`.
  - Golden: regenerated, diff reviewed — every route helper template moves.
- **Doc-comments:** all three templates' gate doc-comments rewritten for the
  role model (the current ones describe the flat `X-User`/`X-Pswd` /
  `<credentials>` gate).

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
