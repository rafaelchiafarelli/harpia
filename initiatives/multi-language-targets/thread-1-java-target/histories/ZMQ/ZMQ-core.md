### Session J.18 — ZMQ core (no CURVE)

- **Depends on:** J.2 merged.
- **Deliverable:** `org.zeromq:jeromq` (pure-Java ZMTP reimplementation —
  no JNI, no native library, no per-platform build) wired for PUSH/PULL/
  PUB/SUB; the origin-id scheme (`_origin_id`, `runtime_origin_id()`)
  ports as the portable algorithm it already is.
- **Out of scope:** CURVE (J.19).
- **Tests:**
  - Integration: client/server ZMQ demo, mirroring the existing C++ one.

## Implementation notes (landed 2026-08-23)

New `JavaZmqAdapter`. Genuinely one shared runtime class
(`runtime/HarpiaZmq.java`: `Sender`/`Receiver`), not the 4 generated
classes per message the C++ target emits — protobuf-java's common
`Message` interface plus JeroMQ's plain `byte[]` send/recv make the whole
transport body generic, so only a thin per-message factory
(`com.harpia.generated.zmq.<name>_zmq`, `ORIGIN_ID` constant +
`newSender`/`newReceiver`/`newPublisher`/`newSubscriber`) needs
generating. Full rationale in `JavaZmqAdapter/CLAUDE.md`.

`ORIGIN_ID`'s derivation and the one-to-*/many-to-* classification are
**imported directly** from `ZmqAdapter.ZmqAdapter` (`_origin_id`,
`_is_one_to_many`) rather than re-implemented — real code reuse across
the C++ and Java target packages, the first time this Java-target work
has depended on a C++-target package's internals (every other adapter so
far only reused `Database.model`, itself already language-agnostic).

`org.zeromq:jeromq:0.6.0` wired into `build.gradle`, the version J.17
confirmed CURVE support against.

Tests: `tests/test_java_zmq.py` — structural checks (pure Python, always
run) plus two gradle+JDK-gated integration tests (PUSH/PULL over
`inproc://` confirming origin stamping; PUB/SUB with the classic "slow
joiner" retried around).