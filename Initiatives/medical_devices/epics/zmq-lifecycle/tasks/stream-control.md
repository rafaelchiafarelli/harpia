## `stream[#]` setup/read/stop + timeout

- **Depends on:** F1 (Foundation). Builds on the already-shipped CURVE
  transport — verify it meets this session's guarantees before extending.
- **Deliverable:** full `stream[#]` lifecycle (setup/read/stop) per the
  process.md spec, with timeout handling.
- **Guarantees:** `read` returns IN-VALID on timeout/stop per spec.
- **Tests:**
  - Unit: invalid stream config → IN-VALID.
  - Integration: extend `test_demo_message_crosses_with_curve`
    (`UnitTests/test_demo.py`) with a timeout scenario — don't duplicate the
    existing CURVE round-trip coverage.
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
