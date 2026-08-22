# Session 2 — Transport & Access

Covers Track C (two rows: mTLS transport, then RBAC/Auth) and Track B
(two rows: ZMQ CURVE, then stream lifecycle). One session handles all
four rows, in order.

---

## Preconditions

Foundation (F1–F5) merged to `main`. Confirm before starting:
- `ComplianceContext` is threaded through `main.py` and every stage.
- `AuditSink` (no-op stub) exists and is injectable.
- `CryptoBackend` selection seam (F5) exists — Track C's TLS stack must
  link against this, not its own crypto library.
- A tagged F4 regression baseline exists.

---

## Execution order

**Track C first (both rows), then Track B (both rows), same session.**
No hard dependency between C and B — the ordering is for focus, not
correctness — but keep them together: Track C sets the credential/session
model the rest of the comm layer should stay consistent with.

Within Track C: do the mTLS transport row before the RBAC/Auth row — auth
sits on top of an authenticated transport, not the other way around.
Within Track B: CURVE security before the stream lifecycle — the
lifecycle work should be built and tested against an already-secured
socket.

---

## Contracts

### Track C — Transport (mTLS) + AuthN/AuthZ (RBAC, sessions)
- **Depends on:** F1, F3, F5.
- **Decision closed: one implementation per project, not one per
  jurisdiction** (`harpia_medical_master_plan.md` §0a). Transport/auth
  behavior is compiled in once, gated by `risk_class` — once it implies
  medical-device-grade, this is the project-wide floor: every message
  gets mTLS/RBAC, not just `phi`/`critical`-tagged ones.
- **Deliverables:** mTLS on gRPC/REST/SOAP; admin/main/guest RBAC
  replacing the flat `X-User`/`X-Pswd` gate; token-based sessions with
  expiry/revocation; cert provisioning scripts in `Assets/`.
- **Guarantees:** plaintext connections refused by default per profile;
  role-based access enforced at the gate with differentiated 401
  (unauthenticated) vs. 403 (wrong role); sessions expire and can be
  revoked.
- **Out of scope:** ZMQ transport (that's Track B).
- **Tests:**
  - Unit: full role × operation permission matrix (allow/deny table).
  - Unit: token expiry and revocation logic.
  - Integration: live REST/gRPC/SOAP calls over TLS with client certs —
    confirm 401 with no cert, 403 with wrong role, 200 with correct role.
  - Acceptance gate: existing HTTP tests (14.7–14.10) updated to run over
    TLS and still pass.

### Track B — ZMQ CURVE security + full stream lifecycle
- **Depends on:** F1.
- **Update (2026-08-18, current harpia `dev` @ `e166317`) — CURVE half
  already shipped, narrower scope remains:**
  - CURVE-secured ZMQ sockets and keypair provisioning in `Assets/` are
    **done** — every generated sender/receiver/publisher/subscriber
    constructor takes a trailing, defaulted `CurveServerKeys`/
    `CurveClientKeys` struct; keys are generated ephemerally at CMake
    configure time via a `try_run`'d probe (`Assets/cmake/
    curve_keygen_probe.cpp`, since no CLI keygen tool ships with apt's
    `libzmq3-dev`), behind a new `-DUSE_ZMQ_CURVE=ON` option. See
    `USAGE.md` §10 and `ZmqAdapter/CLAUDE.md`. Don't re-build this piece —
    verify it meets this track's guarantees below and extend it.
  - **Scoped as encryption-only** (no ZAP client-key allowlist — any
    client with valid CURVE crypto is accepted, TLS-with-no-client-certs'
    analogue, not mTLS). If this compliance context needs *authenticated*
    ZMQ (parity with Track C's RBAC model — i.e. reject a client whose key
    isn't recognized, not just any client with valid crypto), that's a ZAP
    handler on top of what exists, not a rebuild. Decide and scope that
    explicitly before assuming "CURVE" alone satisfies this track's access-
    control needs.
  - **Two real gotchas hit while building this, worth knowing before
    extending it:** (a) Z85-encoded CURVE keys can contain characters
    (`#`/`$`/`(`/`)`/...) that corrupt silently when passed through
    `target_compile_definitions` (a build-system command-line layer like
    GNU Make mangles them) — the fix was writing a generated header
    instead; don't reintroduce compile-definitions for key material. (b)
    `ZMQ_LINGER` defaults to `-1` — a socket with an undelivered message
    from a failed CURVE handshake hangs on destruction forever; relevant
    to the dead-connection-reclamation deliverable below, which will hit
    this same issue for any socket abandoned mid-handshake.
  - **Not yet build-verified on Windows** — `Assets/vcpkg.json`'s
    `zeromq` dependency has the `curve`+`sodium` features added, but
    nothing has been built against them on the native Windows host (this
    matters since "Windows as a generated-code target" is otherwise fully
    verified for every other transport). Flag to whoever has Windows exec
    access.
- **Deliverables (remaining):** full `stream[#]` lifecycle (setup/read/
  stop, timeout, dead-connection reclamation) per the process.md spec, on
  top of the CURVE transport above; a ZAP-based authentication layer if
  this compliance context requires it (see above).
- **Guarantees:** plaintext ZMQ refused by default when the compliance
  profile requires it; `read` returns IN-VALID on timeout/stop per spec;
  abandoned connections reclaimed within the configured window (mind the
  `ZMQ_LINGER` gotcha above for connections abandoned during a handshake).
- **Out of scope:** gRPC/REST/SOAP transport (Track C's job).
- **Tests:**
  - Unit: invalid stream config → IN-VALID; CURVE handshake rejects
    mismatched keys (already covered by `test_zmq_curve_roundtrip` in
    `tests/test_stage13_zmq.py` — extend, don't duplicate).
  - Integration: rerun the existing client/server ZMQ demo with CURVE
    enabled (already covered by `test_demo_message_crosses_with_curve` in
    `tests/test_demo.py`); add a dead-connection/timeout scenario.
  - Acceptance gate: existing ZMQ demo test still passes when the profile
    doesn't require CURVE (backward compatible) — already true today,
    since CURVE is off by default (`-DUSE_ZMQ_CURVE=ON` is opt-in).

---

## Definition of done (applies to every track above)

- Unit tests for every new construct/behavior introduced.
- Integration test covering end-to-end behavior — for Track C, an actual
  mTLS handshake + RBAC-gated request over the wire, not just unit tests
  of cert-loading code in isolation.
- Full F4 regression baseline still passes.
- Track C specifically: one-paragraph note added to `ComplianceReport/`
  describing what changed and why (feeds Track M later).
- No cross-variant parity gate to wait on — Track N's feature-parity diff
  was dropped entirely per `harpia_medical_master_plan.md` §0a (one
  project-wide `risk_class` floor, not per-jurisdiction builds).

## Watch for

- Track N's feature-parity CI diff (the job this used to unblock) was
  dropped entirely per `harpia_medical_master_plan.md` §0a — nothing to
  flag to Session 4 on that front anymore.
- Don't let Track C and Track B run as separate concurrent sessions even
  though they're logically independent — they were deliberately kept on
  one session so the credential model stays consistent, not because of a
  file conflict.
