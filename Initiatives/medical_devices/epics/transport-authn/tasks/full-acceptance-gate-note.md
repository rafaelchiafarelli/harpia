## Full acceptance gate + `ComplianceReport` note

Scoped 2026-08-30. **Task 6** (final) of the transport-authn epic. Mirrors
`dds-transport`'s `full-acceptance-gate-note`.

- **Depends on:** tasks 1–5 merged.
- **Deliverable:** the one-paragraph `ComplianceReport/` traceability note,
  filed as a **process-artifacts** task
  (`process-artifacts-done/tasks/transport-authn-note.md`, same pattern as
  `dds-transport-note.md` / `serialization-redaction-note.md`), per
  `epics/README.md` DoD rule 6 — `ComplianceReport/` is the process-artifacts
  epic's module, not this one's. The note covers mTLS on all three HTTP-family
  transports, the RBAC role model, token sessions, cert provisioning, and (if
  scoped by then) the ZAP allowlist — what changed, why, which tests. Fold into
  `ComplianceReport/requirements.py` if a `transport`-scoped `applies_to` value
  exists by then; otherwise leave the note file and flag the fold as a
  process-artifacts follow-up (same carve-out `dds-transport-note.md` took,
  pending a `dds`-scoped `applies_to`).
- **Acceptance gate:**
  - existing plaintext ZMQ / gRPC / REST / SOAP demo tests still pass with
    `transport_hardening_required` false — this epic is gated, not a hard
    replacement of the plaintext path;
  - with hardening on, end to end: a call with no client cert is refused at the
    transport on all three HTTP-family transports; a call with a valid cert but
    the wrong role gets 403 / PERMISSION_DENIED; a valid cert + correct role
    succeeds;
  - full regression suite green in Docker.
- **Out of scope:** the ZAP allowlist if it has not been scoped into its own
  task by this point — it does not block this epic's gate, it is carried forward
  as a documented deliverable (same posture `dds-transport` kept for
  `deadline[ms]`).

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
