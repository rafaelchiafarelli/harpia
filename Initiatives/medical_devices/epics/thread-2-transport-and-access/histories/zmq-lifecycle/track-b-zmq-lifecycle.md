# Track B — ZMQ CURVE security + full stream lifecycle

**Update (2026-08-18, current harpia `dev` @ `e166317`) — CURVE half
already shipped, narrower scope remains:** CURVE-secured ZMQ sockets and
keypair provisioning in `Assets/` are **done** — every generated
sender/receiver/publisher/subscriber constructor takes a trailing,
defaulted `CurveServerKeys`/`CurveClientKeys` struct; keys are generated
ephemerally at CMake configure time via a `try_run`'d probe
(`Assets/cmake/curve_keygen_probe.cpp`, since no CLI keygen tool ships
with apt's `libzmq3-dev`), behind a new `-DUSE_ZMQ_CURVE=ON` option. See
`USAGE.md` §10 and `ZmqAdapter/CLAUDE.md`. Don't re-build this piece —
verify it meets this track's guarantees and extend it.

**Scoped as encryption-only** (no ZAP client-key allowlist — any client
with valid CURVE crypto is accepted, TLS-with-no-client-certs' analogue,
not mTLS). If this compliance context needs *authenticated* ZMQ (parity
with Track C's RBAC model), that's a ZAP handler on top of what exists
(B.3 below), not a rebuild.

**Two real gotchas hit while building the CURVE half, worth knowing
before extending it:** (a) Z85-encoded CURVE keys can contain characters
that corrupt silently when passed through `target_compile_definitions` —
the fix was writing a generated header instead; don't reintroduce
compile-definitions for key material. (b) `ZMQ_LINGER` defaults to `-1` —
a socket with an undelivered message from a failed CURVE handshake hangs
on destruction forever; relevant to B.2 below, which hits this same issue
for any socket abandoned mid-handshake.

## Receives (must be done before this track starts)

- **F1** from Foundation only (see `../thread-2-transport-and-access/README.md`)
  — unlike Track C, this track does not consume F3 or F5 (the CURVE
  crypto is ZMQ-native, not routed through the `CryptoBackend` seam;
  nothing here calls `AuditSink` per the docs available).
- Nothing from Track C — no file overlap, no functional dependency (see
  the thread README's "Watch for" on why they still run sequentially).

## Gives (what "done" means here, consumed by whom)

- Full `stream[#]` lifecycle (setup/read/stop, timeout, dead-connection
  reclamation) on top of the already-shipped CURVE transport; a ZAP
  authentication layer if this compliance context requires it.
- **Consumed by:** no other track in this thread or documented elsewhere
  in the plan set. **Flag:** the docs don't name a downstream consumer
  for this track's output — not inferring one.

## Files this track touches

- `ZmqAdapter/` (per `harpia_medical_master_plan.md` §2's track table).
  Tests to extend, named explicitly in the docs rather than guessed:
  `UnitTests/test_stage13_zmq.py` (`test_zmq_curve_roundtrip`),
  `UnitTests/test_demo.py` (`test_demo_message_crosses_with_curve`).
  **Flag:** no other specific filenames are named for the remaining
  lifecycle/ZAP work — not guessing further than `ZmqAdapter/`.

---

## Watch for

- B.2's dead-connection reclamation and B.3's ZAP handler (if built) both
  touch handshake-abandonment cases — the `ZMQ_LINGER` gotcha applies to
  both, don't rediscover it twice.
- B.4 doesn't block B.1–B.3 or vice versa — pick it up whenever native
  Windows access is available, independent of this track's other
  sequencing.
