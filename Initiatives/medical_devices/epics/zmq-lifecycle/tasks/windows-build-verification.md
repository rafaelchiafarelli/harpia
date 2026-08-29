## Windows build-verification (existing CURVE feature)

- **Depends on:** nothing from this epic — this verifies the
  **already-shipped** CURVE transport, not task 1–task 3's new work. Can run
  any time, independently of the other sessions in this epic.
- **Constraint, same as the resolved PostgreSQL-on-Windows gap
  (`gaps-not-yet-tracked.md`): needs native Windows exec access.** Not
  build-verified there yet — `Assets/vcpkg.json`'s `zeromq` dependency
  has the `curve`+`sodium` features added, but nothing has been built
  against them on a native Windows host.
- **Deliverable:** build and verify the CURVE-enabled ZMQ demo on native
  Windows (MSVC + vcpkg), same posture as the Postgres-on-Windows
  resolution.
- **Tests:** the build + a real CURVE-enabled client/server exchange on
  Windows *is* the test, same shape as the Postgres resolution's
  container-verified round trip.
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
