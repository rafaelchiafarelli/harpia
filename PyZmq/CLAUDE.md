# PyZmq — the Python target's ZMQ transports

**Pipeline role / purpose:** python-target / py-zmq. The Python side of
`ZmqAdapter/`: a stage of `LangBackend/python.py`'s `run_python`, after
`PyEventsAdapter`.

**Entry point:** `PyZmqAdapter(messages, dest, compliance).Process()` →
`None` (nothing written when no message carries push/pull/event/stream).

**Outputs** (under `<dest>/python/`):
- `harpia_runtime/zmq.py` (from `runtime/zmq.py`): `Sender[M]` (PUSH
  connect / PUB bind with `pub=True`; `send`/`publish` copies the message,
  stamps its `ORIGINATOR*` field — found by name prefix — and sends
  `SerializeToString()` as ONE frame), `Receiver[M]` (PULL bind / SUB
  connect + subscribe-all with `sub=True`; `recv`/`receive` → message or
  `None` on a receive timeout / unparsable frame), `runtime_origin_id()`
  (`<pid>-<counter>-<64 random bits hex>`, the C++ shape). Blocking calls;
  `close()` uses `linger=0`.
- `harpia_generated/zmq/<name>_<hash>_zmq.py` (`templates/zmq.py.tmpl`) for
  exactly the messages C++ emits `zmq/*_zmq.h` for: `ORIGIN_ID` (from
  `ZmqAdapter._origin_id`, imported) and `new_sender` / `new_receiver`
  (PUSH/PULL modifiers) and/or `new_publisher` / `new_subscriber`
  (EVENT/STREAM). Senders default to `ORIGIN_ID` for one-to-* types
  (`ZmqAdapter._is_one_to_many`), else a fresh `runtime_origin_id()` per
  sender; `origin=` overrides.

## Key facts / gotchas
- **Wire = C++ wire:** one serialized-protobuf frame, no envelope. Proven
  by a generated C++ `courier_sender` → Python `new_receiver` test.
- `harpia_runtime.zmq` does `import zmq`; absolute imports mean that is
  pyzmq, not itself.
- PUB/SUB has the classic slow-joiner: tests publish until the
  subscription is live.

## Touchpoints
- Depends on: `ZmqAdapter.ZmqAdapter` (`_modifiers`, `_origin_id`,
  `_is_one_to_many`), `PyAdapter.runtime_copy`.
- Tested by: `UnitTests/test_py_zmq.py`.
