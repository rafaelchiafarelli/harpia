## ZMQ CURVE ZAP client-key allowlist

Scoped 2026-09-01. The deliverable **absorbed from `zmq-lifecycle`** on
2026-08-29 (`transport-authn/README.md`, "ZMQ CURVE ZAP allowlist"), unblocked
now that task 4 (`rbac`) pinned a real identity store. The shipped CURVE
transport is encryption-only: any client with valid CURVE crypto is accepted.
This task adds the identity layer — an allowlist of authorized client public
keys enforced at the ZMTP handshake, the ZMQ analogue of mTLS client-cert
allowlisting.

- **Depends on:** task 4 (`rbac`) merged — the allowlist reads from a
  deployment-config file of the *same shape* as `HARPIA_RBAC_MAP`, it does not
  invent its own store/format/lifecycle (README "Watch for"). `stream-control`
  (zmq-lifecycle) merged for the CURVE seam — it is.
- **Pinned decisions (do not leave implicit):**
  - **Store shape** — the allowlist is read once at startup from the
    `HARPIA_ZMQ_ALLOWLIST` file: one `<z85-client-public-key> <identity>` per
    line, `#` comments, blank lines ignored. `identity` is informational only
    (it correlates a key to the RBAC principal for the audit trail; ZAP itself
    authorizes on the key). Deployment config, **not** schema, **not**
    compiled-in — identical posture to `HARPIA_RBAC_MAP`. Absent/empty file →
    see fail-safe.
  - **Gating** — the ZAP handler is compiled/started only when
    `Crypto.backend.transport_hardening_required(compliance)` is true (same
    project-wide floor as mTLS / RBAC, never per-jurisdiction, §0a). Non-hardened
    builds are byte-identical to today.
  - **Fail-safe** — hardened + `CURVE_SERVER` socket + no allowlist file (or an
    empty one) → **every** client key is denied (the handshake fails), never
    "allow all". One `AuditSink` record per denial (`"zap_denied"`, z85 key +
    identity metadata only, never secret key material — Rule 5).
  - **Lifecycle** — ZAP is per-`zmq::context_t`, but the generated
    `<name>_receiver` / `<name>_publisher` each construct their own socket
    independently with no shared owner object. The handler is therefore
    **lazily started per context** via a `harpia::zap::ensure_running(ctx)`
    call injected into the CURVE-server apply snippet (a process-wide
    `static` registry keyed on the context pointer — same technique as
    `harpia::rbac::role_map()`'s lazy static). It binds a `REP` socket on
    `inproc://zeromq.zap.01` on a background thread, joined on context
    shutdown.
- **Deliverable:**
  - `Compliance/runtime/harpia_zap.h` (hand-written C++, copied verbatim like
    `harpia_rbac.h` / `harpia_audit_sink.h`): `harpia::zap` — `AllowList`
    (`from_env()`, `contains(z85_key)`), `ZapHandler` (the `inproc://zeromq.zap.01`
    REP loop: reads a ZAP 1.0 request, replies `200`/`400` on the CURVE
    credential's key, `record("zap_denied", …)` on a `400`), and
    `ensure_running(::zmq::context_t&)`. `#include`s `harpia_audit_sink.h`.
  - `Compliance/zap_common.py` — `ZAP_RUNTIME` / `ZAP_RUNTIME_SRC` /
    `ZAP_RUNTIME_DEPS` path constants (mirrors `rbac_common.py`).
  - `ZmqAdapter/ZmqAdapter.py` — when hardened, the `_CURVE_SERVER_APPLY`
    snippet gains a `::harpia::zap::ensure_running(ctx);` line (before
    `curve_server` is set), and `ZmqAdapter` copies `harpia_zap.h` +
    `harpia_audit_sink.h` into `generated/cpp/zap/` (only when a CURVE-server
    socket is emitted under a hardened profile). Connect-side sockets
    (`_CURVE_CLIENT_APPLY`) are untouched.
  - **Provisioning** — extend `Assets/cmake/` with a small keygen/allowlist
    helper (`zmq_zap_provision.sh` or fold into the existing CURVE keygen
    probe) that emits a client keypair + an `HARPIA_ZMQ_ALLOWLIST` line, so
    the demo and tests have real keys to allow/deny. Not an integration with
    an external key store (same dev/bootstrap boundary as `mtls_provision.sh`).
- **Out of scope:** rotation/revocation tooling beyond "edit the file and
  restart"; a ZAP `DOMAIN`/PLAIN mechanism (CURVE only); the Java ZMQ target
  (`JavaZmqAdapter` — CURVE there is already flagged lower-confidence);
  per-message allowlists (one per project).
- **Tests:** `UnitTests/test_zmq_zap.py` —
  - Unit / structural (pure Python): a hardened generation injects
    `ensure_running` into the CURVE-server apply and copies `zap/harpia_zap.h`;
    a non-hardened generation does neither (byte-identical headers).
  - g++-gated, standalone against `harpia_zap.h`: `AllowList::from_env()`
    parses the file (comments/blanks); `contains()` is exact-match on the
    z85 key; a missing file yields an empty list (deny-all).
  - libzmq+cppzmq-gated, real `tcp://` (CURVE is a no-op over `inproc`, same
    discipline as `test_stage13_zmq.py::test_zmq_curve_roundtrip`): an
    allowlisted client key completes the handshake and exchanges a message;
    a non-allowlisted key with otherwise-valid CURVE crypto never receives
    anything (bounded timeout, not a hang) and produces exactly one
    `"zap_denied"` `AuditSink` record carrying the z85 key + identity, never
    secret material.
  - `test_stage13_zmq.py` pinned to a low-risk profile so its existing CURVE
    round-trip keeps exercising the encryption-only path (the ZAP path is
    this task's test's job) — mirrors what task 4 did to `test_stage11/12/13`.
  - Golden regen: `UnitTests/golden/zmq/` (CURVE-server headers gain the
    `ensure_running` line under the repo's hardened profile; `zap/harpia_zap.h`
    is snapshotted like `grpc/harpia_grpc_mtls.h`).
- **Doc-comments / docs:** `header.h.tmpl`'s CURVE comment updated for the
  allowlist; `ZmqAdapter/CLAUDE.md` + `Compliance/CLAUDE.md` updated;
  `transport-authn/README.md`'s "not yet task-scoped" note resolved;
  `USAGE.md` §10 gains the allowlist wiring.
