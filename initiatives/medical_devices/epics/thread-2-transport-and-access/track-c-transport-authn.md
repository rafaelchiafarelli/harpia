# Track C — Transport (mTLS) + AuthN/AuthZ (RBAC, sessions)

**Decision closed: one implementation per project, not one per
jurisdiction** (`harpia_medical_master_plan.md` §0a). Transport/auth
behavior is compiled in once, gated by `risk_class` — once it implies
medical-device-grade, this is the project-wide floor: every message gets
mTLS/RBAC, not just `phi`/`critical`-tagged ones.

## Receives (must be done before this track starts)

- **F1, F3, F5** from Foundation (see `../thread-2-transport-and-access/README.md`)
  — `ComplianceContext`, `AuditSink` stub, and the `CryptoBackend`
  selection seam this track's TLS stack must link against (not its own
  crypto library).
- Nothing from Track B — no file overlap, no functional dependency (see
  `track-b-zmq-lifecycle.md`'s own Receives section, and the thread
  README's "Watch for" on why they still run sequentially anyway).

## Gives (what "done" means here, consumed by whom)

- mTLS on gRPC/REST/SOAP; admin/main/guest RBAC replacing the flat
  `X-User`/`X-Pswd` gate; token-based sessions with expiry/revocation;
  cert provisioning scripts.
- **Consumed by:** Track Q (`../thread-5-device-interop/histories/sdc-biceps/track-q-sdc-biceps.md`)
  — its IEEE 11073 SDC/BICEPS work explicitly leans on "the same
  credential model Track C is hardening" for its SOAP/MDPWS work.
  **Flag:** as of the message-versioning effort (shipped, since deleted
  from `initiatives/` — see `HttpCapabilityAdapter/CLAUDE.md`), no other
  shipped code consumes Track C yet — its session/login mechanism
  doesn't exist in the real codebase, which is why that effort's
  capability handshake built its own standalone REST/SOAP mechanism
  instead of piggybacking on this track. See the thread README's
  "Watch for."

## Files this track touches

- `ProtoFile/` (specifically `GrpcCompiler.py`), `Assets/` (cert
  provisioning scripts), and "generated gate code" (per
  `harpia_medical_master_plan.md` §2's track table — the docs don't name
  the specific gate-code files beyond that description). **Flag:** no
  more specific filenames for the REST/SOAP/gRPC credential-gate code
  itself are named in the plan docs — not guessing which files those are.

---

## Session C.1 — Cert provisioning scripts

- **Depends on:** F5 (Foundation) — links against the `CryptoBackend`
  seam, doesn't pick its own crypto module.
- **Deliverable:** cert provisioning scripts in `Assets/`, shared
  prerequisite for all three transports' mTLS work below.
- **Out of scope:** wiring certs into any actual transport (C.2/C.3).
- **Tests:**
  - Unit: script produces a valid cert/key pair consumable by the
    `CryptoBackend` seam's selected module.

## Session C.2 — mTLS on gRPC

- **Depends on:** C.1 merged; F1, F3 (Foundation).
- **Deliverable:** mTLS on the gRPC transport; plaintext gRPC connections
  refused by default per compliance profile.
- **Tests:**
  - Integration: live gRPC call over TLS with client certs — 401-
    equivalent (connection refused) with no cert, 200-equivalent with a
    valid cert.

## Session C.3 — mTLS on REST/SOAP

- **Depends on:** C.1 merged; F1, F3 (Foundation).
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
    same refuse-without-cert / accept-with-cert behavior as C.2.

## Session C.4 — RBAC (admin/main/guest)

- **Depends on:** C.2, C.3 merged — "auth sits on top of an authenticated
  transport, not the other way around" (per the original session-2
  ordering note this file replaces).
- **Deliverable:** admin/main/guest RBAC replacing the flat
  `X-User`/`X-Pswd` gate, across all three transports.
- **Guarantees:** role-based access enforced at the gate with
  differentiated 401 (unauthenticated) vs. 403 (wrong role).
- **Tests:**
  - Unit: full role × operation permission matrix (allow/deny table).
  - Integration: live calls confirm 401 with no cert, 403 with wrong
    role, 200 with correct role, across gRPC/REST/SOAP.

## Session C.5 — Token-based sessions with expiry/revocation

- **Depends on:** C.4 merged.
- **Deliverable:** token-based sessions layered on top of the RBAC gate,
  with expiry and revocation.
- **Tests:**
  - Unit: token expiry and revocation logic.

## Session C.6 — Full acceptance gate + `ComplianceReport` note

- **Depends on:** C.1–C.5 merged.
- **Deliverable:** one-paragraph `ComplianceReport/` note describing what
  changed and why (feeds Track M later).
- **Acceptance gate:** existing HTTP tests (14.7–14.10) updated to run
  over TLS and still pass.

## Watch for

- Within this track: mTLS (C.2/C.3) before RBAC (C.4), RBAC before
  sessions (C.5) — each session above already encodes this via its
  `Depends on` line, but don't reorder them even though C.2 and C.3
  themselves have no dependency on each other and could run in either
  order (or in parallel, if split across two session-lines).
