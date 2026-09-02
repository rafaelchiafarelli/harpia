## Token-based sessions with expiry / revocation

**Done 2026-09-01.** Mechanism pinned: hand-written
`Compliance/runtime/harpia_session.h` (`harpia::session`), copied verbatim into
`generated/cpp/{http,grpc}/` next to `harpia_rbac.h` by the same two adapters
under the same `transport_hardening_required(compliance)` gate (path constants
in `Compliance/session_common.py`). Token = `v1.<b64url(payload)>.<hmac-sha256
hex>`, payload `cn\nrole\niat\nexp\njti` (jti = 128-bit `RAND_bytes`);
`issue(cn, role, ttl, now)` / `decode()` / `verify() -> Verdict{ok, no_key,
malformed, bad_signature, expired, revoked}` / `from_authorization("Bearer …")`
for the gates. Signing key + TTL + revocation file are deployment config read
once from the environment (`HARPIA_SESSION_KEY` — raw or `@<path>`, empty ⇒
sessions disabled; `HARPIA_SESSION_TTL` default 900;
`HARPIA_SESSION_REVOCATIONS` re-read whenever its contents change,
`std::mutex`-guarded), same posture as `HARPIA_RBAC_MAP`. Signing is real
HMAC-SHA256 over a **self-contained SHA-256 bundled in the header** (FIPS-180-4
/ RFC-4231 vectors checked in `test_sessions.py`) — deliberately not an OpenSSL
call, so `harpia_session.h` stays pure-std and links anywhere `harpia_rbac.h`
does (chosen after the OpenSSL route broke the plain-consumer / `test_stage14`
link, which never link `-lcrypto`). Which crypto module a project is *validated*
against is still the F5 seam's call, recorded next door in
`{http,grpc}_server_selection.json`, so no new selection file. Every non-ok
`verify()` emits exactly one `AuditSink` `"session_denied"` record
(verdict/cn/jti metadata, never token bytes — Rule 5).

Gate wiring (`Database/auth_gate.py`, `rbac=True` branch only, so the flat
variant is byte-identical): each RBAC gate first calls
`session::from_authorization()` on the `Authorization: Bearer` header
(REST/SOAP) / `authorization` metadata (gRPC); a token that verifies supplies
the CN `rbac::decide()` runs on, in place of the client cert; a
presented-but-invalid token is refused outright (401 / UNAUTHENTICATED), never
a fall-through to the cert. Issuance: REST `POST <rest_base>/session` (JSON
`{"token":…}`) and SOAP `POST <soap_base>/session` (`<sessionToken>` envelope)
spliced into `http_server_bringup.h`'s new `register_session()` by
`RestAdapter`; gRPC `heartBeat` mints a `harpia-session-token` trailing-metadata
value when the call carries `harpia-issue-session` metadata (new
`{hb_ctx}`/`{session_issue}` template fills — empty in the flat variant).
`HttpCapabilityAdapter/`'s standalone session mechanism was **not** reconciled
(flagged optional; deferred — it is a capability-advertisement path, not an
auth session, and touching it is out of this task's scope).

Tests: `UnitTests/test_sessions.py` — unit (g++ + `-lcrypto`): issue/verify
round trip + role-matches-identity, expiry, revocation (+ list re-read both
ways), MAC-flip / body-splice / malformed / no-key rejection, one
`session_denied` audit record per non-ok with no token bytes leaked;
integration REST+SOAP over mTLS (a `mint` helper fabricates deterministically
expired tokens): `POST /session` issuance, an admin token used from a guest
cert gets the admin verbs, tampered/expired/revoked → 401; integration gRPC
over mTLS: `heartBeat` issuance, `push` with `authorization: Bearer` on a guest
channel succeeds, bad token → UNAUTHENTICATED. Golden regenerated (rest/soap/grpc
headers + both bring-ups gain the session path; new `{http,grpc}/harpia_session.h`).
Doc-comments: `harpia_session.h` top comment (the obtain/present/expiry/revoke
flow), all three transport templates' gate comments, both bring-up templates.

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
