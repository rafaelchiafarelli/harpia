### Session J.19 — CURVE-secured ZMQ variant

- **Depends on:** J.17 (confirmed CURVE support) and J.18 merged. If J.17
  found CURVE unsupported on the pinned version, this session doesn't
  proceed as scoped — flag and re-plan rather than force it.
- **Deliverable:** CURVE-secured variant of J.18's transport.
- **Tests:**
  - Integration: CURVE-enabled client/server exchange.

## Implementation notes (landed 2026-08-23)

`HarpiaZmq.CurveKeys` (in J.18's shared runtime file, `runtime/HarpiaZmq.
java`) — one class, two named factory methods (`server(secretKey)` /
`client(serverPublicKey, publicKey, secretKey)`) replacing the C++
runtime's two separate `CurveServerKeys`/`CurveClientKeys` structs.
`generateCurveKeyPair()` wraps `org.zeromq.ZMQ.Curve.generateKeyPair()`
(Z85-encoded strings) with a `z85Decode` step so callers get raw bytes
directly, matching what the socket-option setters actually want. Every
`com.harpia.generated.zmq.<name>_zmq` factory method gained a CURVE-taking
overload; the plain overloads are untouched (empty/absent curve = today's
J.18 plaintext behavior, unchanged).

**Confidence caveat, stated plainly (see `JavaZmqAdapter/CLAUDE.md` for
the full version):** the exact `org.zeromq.ZMQ.Curve` API shape is sourced
from web research (public javadoc/source/examples across JeroMQ
0.4.3-0.5.2) — not compiled or run here, since this environment has no
JDK/JeroMQ jar. This session's own integration test
(`tests/test_java_zmq_curve.py`) is where a real handshake finally proves
it, whenever it runs somewhere with a JVM; if that disagrees with what's
implemented here, this file and `JavaZmqAdapter/CLAUDE.md` are where to
correct the record, not silently patch over it.

Tests: `tests/test_java_zmq_curve.py` -- structural checks (pure Python,
always run) plus two gradle+JDK-gated integration tests, both over real
`tcp://` (CURVE is a no-op over `inproc://`, the transport J.18's own
tests use): matching keys complete a handshake and exchange a message; a
client given the wrong server public key never receives anything.