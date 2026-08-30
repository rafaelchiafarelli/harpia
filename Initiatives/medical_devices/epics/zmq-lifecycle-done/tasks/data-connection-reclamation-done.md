## Dead-connection reclamation

Scoped 2026-08-29. **Task 2** of the zmq-lifecycle epic.

### Decisions (settled during scoping — do not re-litigate)

- **Synchronous reclamation, no background thread.** The sweep runs inside
  `read()`, `stop()`, and the destructor — never on a timer thread. This
  matches the caller-synchronized / not-thread-safe contract the rest of the
  comm + delivery layer holds (`harpia_delivery.h`,
  `harpia_capability_dispatch.h`).
- **The reclamation window is `StreamConfig.reclaim_after_ms`** (declared in
  task 1's `StreamConfig`), not a new CMake option or `.harpia` declaration.

### Contract

- **Depends on:** task 1 (`stream-control`) merged — uses the `<name>_stream`
  class, its `StreamConfig.reclaim_after_ms`, and its teardown path.
- **Deliverable:** on every `read()` / `stop()` / destructor call, any stream
  connection that has had no successful `read()` and no keepalive within
  `reclaim_after_ms` is torn down (`ZMQ_LINGER=0`, then close); a subsequent
  `read()` on a reclaimed stream returns `StreamStatus::INVALID`.
  "Abandoned mid-handshake" = a `setup()`'d stream whose CURVE handshake
  never completed and which delivered no message within `reclaim_after_ms`.
- **No hang on destruction** — the `ZMQ_LINGER` default of `-1` makes a
  socket with an undelivered failed-handshake message hang forever; set
  `ZMQ_LINGER=0` before the reclaim close, same as task 1's teardown.

**Tests:**
- Integration: extend the task-1 demo — `setup()` a stream pointed at a dead
  endpoint (handshake never completes), do **not** call `stop()`, advance
  past `reclaim_after_ms`, assert the next `read()` returns `INVALID` and
  that object destruction does not hang.

---
## Epic context — zmq-lifecycle

**Contract.** Full `stream` lifecycle (setup/read/stop, timeout, dead-connection
reclamation) on top of the already-shipped CURVE transport. Needs only
`ComplianceContext` from Foundation. No downstream consumer named. (The ZAP
client-key allowlist that used to round out this epic moved to the
transport-authn epic on 2026-08-29 — see that epic's README.)

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
the dead-connection reclamation sweep.
