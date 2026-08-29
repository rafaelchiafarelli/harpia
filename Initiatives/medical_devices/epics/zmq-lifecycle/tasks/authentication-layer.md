## ZAP authentication layer (conditional)

- **Depends on:** task 1 merged. **Decide before building:** only needed if
  this compliance context requires authenticated ZMQ (rejecting a client
  whose key isn't recognized, not just any client with valid CURVE
  crypto) — not a default part of every deployment. Confirm the
  requirement before starting this session rather than assuming CURVE
  alone is insufficient.
- **Deliverable:** a ZAP handler on top of the existing CURVE transport,
  enforcing a client-key allowlist.
- **Tests:**
  - Unit: ZAP handler rejects a client whose key isn't on the allowlist,
    even with valid CURVE crypto.
---
## Epic context — zmq-lifecycle

**Contract.** Full `stream[#]` lifecycle (setup/read/stop, timeout, dead-connection
reclamation) on top of the already-shipped CURVE transport, plus a ZAP
authentication layer if this compliance context requires authenticated ZMQ.
Needs only `ComplianceContext` from Foundation. No downstream consumer named.

**Already shipped, verify only:** CURVE-secured sockets + ephemeral keypair
provisioning (`-DUSE_ZMQ_CURVE=ON`, `Assets/cmake/curve_keygen_probe.cpp`). See
`USAGE.md` §10 and `ZmqAdapter/CLAUDE.md`. Do not rebuild.

**Files.** `ZmqAdapter/`. Tests to extend: `UnitTests/test_stage13_zmq.py`
(`test_zmq_curve_roundtrip`), `UnitTests/test_demo.py`
(`test_demo_message_crosses_with_curve`).

**Watch for.** (a) Z85 CURVE keys corrupt silently through
`target_compile_definitions` — use a generated header, never compile-definitions
for key material. (b) `ZMQ_LINGER` defaults to `-1`: a socket with an undelivered
message from a failed handshake hangs on destruction forever — applies to
dead-connection reclamation and the ZAP handler both.
