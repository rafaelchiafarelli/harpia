# Transport (mTLS) + AuthN/AuthZ (RBAC, sessions) + ZMQ CURVE identity

**Decision closed: one implementation per project, not one per
jurisdiction** (`harpia_medical_master_plan.md` §0a). Transport/auth
behavior is compiled in once, gated by `risk_class` — once it implies
medical-device-grade, this is the project-wide floor: every message gets
mTLS/RBAC, not just `phi`/`critical`-tagged ones.

**Absorbed 2026-08-29:** the ZMQ **ZAP client-key allowlist** (was
`zmq-lifecycle`'s `authentication-layer` task) is folded in here — this epic
owns the project's identity / credential / provisioning model across *every*
transport, and a ZAP allowlist is that model applied to the raw-socket path
(the shipped CURVE transport is encryption-only, no identity). Same
reasoning that moved `versioning` into `process-artifacts`: put the work
where the model it depends on actually lives. `zmq-lifecycle` is now a
clean 3-task epic (`stream-control`, `data-connection-reclamation`,
`windows-build-verification`).

## Receives (must be done before this epic starts)

- **F1, F3, F5** from Foundation (see `../README.md`)
  — `ComplianceContext`, `AuditSink` stub, and the `CryptoBackend`
  selection seam this epic's TLS stack must link against (not its own
  crypto library).
- Nothing *functional* from the zmq-lifecycle epic. Note the ZAP-allowlist
  work absorbed from it (above) does touch `ZmqAdapter/`, on top of the
  already-shipped CURVE transport (`-DUSE_ZMQ_CURVE=ON`) — but no
  zmq-lifecycle *task* is a prerequisite; `stream-control` merged is enough
  to have the CURVE seam in place.

## Gives (what "done" means here, consumed by whom)

- mTLS on gRPC/REST/SOAP; admin/main/guest RBAC replacing the flat
  `X-User`/`X-Pswd` gate; token-based sessions with expiry/revocation;
  cert provisioning scripts.
- **ZMQ CURVE identity:** a ZAP handler on the `CURVE_SERVER` sockets
  enforcing an allowlist of authorized client public keys — rejecting an
  unrecognized key even when its CURVE crypto is valid (the ZMQ analogue of
  mTLS client-cert allowlisting). Allowlist source / provisioning / rotation
  / revocation share this epic's credential model, not a bespoke one.
- **Consumed by:** the sdc-biceps epic (`../sdc-biceps/README.md`)
  — its IEEE 11073 SDC/BICEPS work explicitly leans on "the same
  credential model the transport-authn epic is hardening" for its SOAP/MDPWS work.
  **Flag:** as of the message-versioning effort (shipped, since deleted
  from `Initiatives/` — see `HttpCapabilityAdapter/CLAUDE.md`), no other
  shipped code consumes the transport-authn epic yet — its session/login mechanism
  doesn't exist in the real codebase, which is why that effort's
  capability handshake built its own standalone REST/SOAP mechanism
  instead of piggybacking on this epic. See epics/README.md's
  "Watch for."

## Files this epic touches

- `ProtoFile/` (specifically `GrpcCompiler.py`), `Assets/` (cert
  provisioning scripts), and "generated gate code" (per
  `harpia_medical_master_plan.md` §2's epic table — the docs don't name
  the specific gate-code files beyond that description). **Flag:** no
  more specific filenames for the REST/SOAP/gRPC credential-gate code
  itself are named in the plan docs — not guessing which files those are.
- `ZmqAdapter/` — for the absorbed ZAP-allowlist work (a ZAP handler +
  allowlist wiring on the shipped CURVE sockets; see
  `ZmqAdapter/CLAUDE.md`'s "CURVE encryption (encryption-only, no ZAP
  allowlist)" note for exactly what is and isn't there today).

---

## Cert provisioning scripts

- **Depends on:** F5 (Foundation) — links against the `CryptoBackend`
  seam, doesn't pick its own crypto module.
- **Deliverable:** cert provisioning scripts in `Assets/`, shared
  prerequisite for all three transports' mTLS work below.
- **Out of scope:** wiring certs into any actual transport (task 2/task 3).
- **Tests:**
  - Unit: script produces a valid cert/key pair consumable by the
    `CryptoBackend` seam's selected module.

## mTLS on gRPC

- **Depends on:** task 1 merged; F1, F3 (Foundation).
- **Deliverable:** mTLS on the gRPC transport; plaintext gRPC connections
  refused by default per compliance profile.
- **Tests:**
  - Integration: live gRPC call over TLS with client certs — 401-
    equivalent (connection refused) with no cert, 200-equivalent with a
    valid cert.

## mTLS on REST/SOAP

- **Depends on:** task 1 merged; F1, F3 (Foundation).
- **Deliverable:** mTLS on REST and SOAP together, not as two separate
  efforts — reuse the precedent `HttpCapabilityAdapter/CLAUDE.md` already
  established for this exact pairing: REST/SOAP already share one
  `crow::SimpleApp` (`Database/RestAdapter.py`/`SoapAdapter.py` both take
  a `crow::SimpleApp&`), so building a SOAP-envelope-specific mTLS path
  separate from REST's would be pure duplication for zero new coverage,
  the same reasoning that produced `HttpCapabilityAdapter/` as one shared
  mechanism rather than two.
- **Tests:**
  - Integration: live REST and SOAP calls over TLS with client certs —
    same refuse-without-cert / accept-with-cert behavior as task 2.

## RBAC (admin/main/guest)

- **Depends on:** task 2, task 3 merged — "auth sits on top of an authenticated
  transport, not the other way around".
- **Deliverable:** admin/main/guest RBAC replacing the flat
  `X-User`/`X-Pswd` gate, across all three transports.
- **Guarantees:** role-based access enforced at the gate with
  differentiated 401 (unauthenticated) vs. 403 (wrong role).
- **Tests:**
  - Unit: full role × operation permission matrix (allow/deny table).
  - Integration: live calls confirm 401 with no cert, 403 with wrong
    role, 200 with correct role, across gRPC/REST/SOAP.

## Token-based sessions with expiry/revocation

- **Depends on:** task 4 merged.
- **Deliverable:** token-based sessions layered on top of the RBAC gate,
  with expiry and revocation.
- **Tests:**
  - Unit: token expiry and revocation logic.

## ZMQ CURVE ZAP allowlist  (absorbed from zmq-lifecycle, not yet task-scoped)

- **Depends on:** the RBAC / credential model (task 4) far enough along that
  "authorized identities" has a concrete source — the ZAP allowlist must
  read from *that*, not invent its own store/format/lifecycle. `stream-control`
  (zmq-lifecycle task 1) merged for the CURVE seam.
- **Deliverable:** a ZAP handler bound to `inproc://zeromq.zap.01` on the
  generated `CURVE_SERVER` sockets (PULL receiver / PUB publisher /
  `<name>_stream`), consulting an allowlist of authorized client public
  keys; an unrecognized key is rejected at the handshake even with valid
  CURVE crypto. One selection per project, gated by `risk_class` /
  compliance profile — never per-jurisdiction (§0a) — same posture as mTLS.
- **Open (decide when scoping):** allowlist provisioning / rotation /
  revocation must reuse this epic's cert/identity provisioning, not the
  `Assets/cmake/curve_keygen_probe.cpp` ephemeral-keypair path (that's a
  demo convenience, not an identity store).
- **Out of scope:** changing the CURVE *encryption* layer (shipped, verify
  only) or the `stream` lifecycle itself (zmq-lifecycle tasks 1–2, done).
- **Tests:** Unit — the ZAP handler rejects a client whose key isn't on the
  allowlist even with valid CURVE crypto; accepts one that is. Integration —
  extend `UnitTests/test_stage13_zmq.py::test_zmq_curve_roundtrip` /
  `test_demo.py` with an allowlist-miss case (`ZMQ_LINGER=0` on both sides —
  a rejected handshake leaves an undeliverable message that hangs
  destruction otherwise, same gotcha as the CURVE and stream work).

## Watch for

- Within this epic: mTLS (task 2/task 3) before RBAC (task 4), RBAC before
  sessions (task 5) — each session above already encodes this via its
  `Depends on` line, but don't reorder them even though task 2 and task 3
  themselves have no dependency on each other and could run in either
  order (or in parallel, if split across two session-lines).
- The **ZAP allowlist** section above is deliberately *not* broken into a
  numbered task yet — it needs this epic's own credential model to exist
  first (the exact reason it was moved out of zmq-lifecycle). Scope it once
  task 4's identity store is real; until then it stays a documented
  deliverable, not a ready task.
