# Transport (mTLS) + AuthN/AuthZ (RBAC, sessions)

**Decision closed: one implementation per project, not one per
jurisdiction** (`harpia_medical_master_plan.md` §0a). Transport/auth
behavior is compiled in once, gated by `risk_class` — once it implies
medical-device-grade, this is the project-wide floor: every message gets
mTLS/RBAC, not just `phi`/`critical`-tagged ones.

## Receives (must be done before this epic starts)

- **F1, F3, F5** from Foundation (see `../README.md`)
  — `ComplianceContext`, `AuditSink` stub, and the `CryptoBackend`
  selection seam this epic's TLS stack must link against (not its own
  crypto library).
- Nothing from the zmq-lifecycle epic — no file overlap, no functional dependency (see
  the zmq-lifecycle epic's own Receives section, and the thread
  README's "Watch for" on why they still run sequentially anyway).

## Gives (what "done" means here, consumed by whom)

- mTLS on gRPC/REST/SOAP; admin/main/guest RBAC replacing the flat
  `X-User`/`X-Pswd` gate; token-based sessions with expiry/revocation;
  cert provisioning scripts.
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

## Full acceptance gate + `ComplianceReport` note

- **Depends on:** task 1–task 5 merged.
- **Deliverable:** one-paragraph `ComplianceReport/` note describing what
  changed and why (feeds the process-artifacts epic later).
- **Acceptance gate:** existing HTTP tests (14.7–14.10) updated to run
  over TLS and still pass.

## Watch for

- Within this epic: mTLS (task 2/task 3) before RBAC (task 4), RBAC before
  sessions (task 5) — each session above already encodes this via its
  `Depends on` line, but don't reorder them even though task 2 and task 3
  themselves have no dependency on each other and could run in either
  order (or in parallel, if split across two session-lines).
