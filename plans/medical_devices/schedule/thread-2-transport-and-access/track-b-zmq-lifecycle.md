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
  `tests/test_stage13_zmq.py` (`test_zmq_curve_roundtrip`),
  `tests/test_demo.py` (`test_demo_message_crosses_with_curve`).
  **Flag:** no other specific filenames are named for the remaining
  lifecycle/ZAP work — not guessing further than `ZmqAdapter/`.

---

## Session B.1 — `stream[#]` setup/read/stop + timeout

- **Depends on:** F1 (Foundation). Builds on the already-shipped CURVE
  transport — verify it meets this session's guarantees before extending.
- **Deliverable:** full `stream[#]` lifecycle (setup/read/stop) per the
  process.md spec, with timeout handling.
- **Guarantees:** `read` returns IN-VALID on timeout/stop per spec.
- **Tests:**
  - Unit: invalid stream config → IN-VALID.
  - Integration: extend `test_demo_message_crosses_with_curve`
    (`tests/test_demo.py`) with a timeout scenario — don't duplicate the
    existing CURVE round-trip coverage.

## Session B.2 — Dead-connection reclamation

- **Depends on:** B.1 merged.
- **Deliverable:** abandoned connections reclaimed within a configured
  window. Mind the `ZMQ_LINGER` gotcha above — a socket abandoned
  mid-handshake will hang on destruction under the default `-1` linger
  unless this is handled explicitly.
- **Tests:**
  - Integration: extend the existing demo test with a dead-connection
    scenario (socket abandoned mid-handshake), confirm reclamation within
    the configured window and no hang on destruction.

## Session B.3 — ZAP authentication layer (conditional)

- **Depends on:** B.1 merged. **Decide before building:** only needed if
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

## Session B.4 — Windows build-verification (existing CURVE feature)

- **Depends on:** nothing from this track — this verifies the
  **already-shipped** CURVE transport, not B.1–B.3's new work. Can run
  any time, independently of the other sessions in this track.
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

## Watch for

- B.2's dead-connection reclamation and B.3's ZAP handler (if built) both
  touch handshake-abandonment cases — the `ZMQ_LINGER` gotcha applies to
  both, don't rediscover it twice.
- B.4 doesn't block B.1–B.3 or vice versa — pick it up whenever native
  Windows access is available, independent of this track's other
  sequencing.
