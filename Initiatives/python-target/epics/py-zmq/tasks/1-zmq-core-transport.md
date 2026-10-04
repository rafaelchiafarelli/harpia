## ZMQ core: PUSH/PULL + PUB/SUB over `pyzmq`, origin ids, ORIGINATOR stamping

- **Depends on:** `py-foundation` (all).
- **Contract:**
  - `harpia_runtime/zmq.py`, generic over any message (one shared runtime,
    as in `JavaZmqAdapter/CLAUDE.md`):
    - `Sender` (PUSH connect / PUB bind) stamps the `ORIGINATOR*` field
      (found by name prefix) and then sends `SerializeToString()` as one
      frame;
    - `Receiver` (PULL bind / SUB connect + subscribe-all) parses one
      frame into a fresh message;
    - blocking calls (no `NOBLOCK`), matching C++;
    - `runtime_origin_id()` is pid + per-process counter + `secrets` bits.
  - Generated `harpia_generated/zmq/<name>_<hash>_zmq.py` per
    transport-bearing message (same filter as `ZmqAdapter`: PUSH/PULL →
    sender/receiver, EVENT/STREAM → publisher/subscriber). It holds:
    - `ORIGIN_ID`, from `ZmqAdapter.ZmqAdapter._origin_id`, **imported**
      and not re-derived, as Java does;
    - factory functions `new_sender`/`new_receiver`/`new_publisher`/
      `new_subscriber`, only for the roles the modifiers call for;
    - one-to-* messages use `ORIGIN_ID`; many-to-* messages call
      `runtime_origin_id()` per constructed sender.
- **Bar:** wire frames are identical to C++'s (one serialized-protobuf
  frame, no envelope), so C++ and Python peers interoperate.
- **Out of scope:** CURVE/ZAP (2), `critical` (3), `stream` (4).
- **Tests:**
  - Generated-project round-trips (inproc and tcp) for push/pull and
    pub/sub.
  - N-peer fan-out (every subscriber gets every message) and push/pull
    load-balance (each message is delivered exactly once across pullers),
    Python-only, mirroring the C++ multipeer tests.
  - A protoc+g++-gated C++-sender → Python-receiver case.
