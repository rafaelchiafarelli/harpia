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

## CURVE + ZAP (task 2)
- `harpia_runtime.zmq`: `CurveServerKeys(secret_key)` (bind side: PULL
  receiver / PUB publisher) and `CurveClientKeys(server_public_key,
  public_key, secret_key)` (connect side), Z85 strings; empty → plaintext;
  the wrong type for a side raises `TypeError`. `generate_curve_keypair()`.
  Every socket is created with `linger=0`. Generated factories take a
  trailing `curve=` typed for their side.
- `runtime/zap.py` → `harpia_runtime.zap` (copied, with the audit sink, only
  under `transport_hardening_required(compliance)`, like C++'s `zap/`):
  `AllowList` (`HARPIA_ZMQ_ALLOWLIST`, C++ format and comment rule),
  `ZapHandler` (hand-written REP loop on `inproc://zeromq.zap.01`, one daemon
  thread, `RCVTIMEO` 250 ms, inert if the endpoint is taken),
  `ensure_running(ctx, audit_sink=None)` (one per context, `WeakKeyDictionary`
  — never keyed by `id()`, whose reuse could leave a new context without a
  handler, i.e. fail-open). Denials record `("zap_denied",
  "inproc://zeromq.zap.01", "key=<z85> [identity=<id>] mechanism=<m>")`.
  Hardened generated bind-side factories pass `zap=True`, which starts the
  handler before `CURVE_SERVER` is set.
- **Decision (task 2):** not `zmq.auth.ThreadAuthenticator` — it reads
  certificate directories and has no audit hook.
- No real CURVE public key can START with `#` (first Z85 digit is
  ⌊word/85⁴⌋ ≤ 82; `#` is digit 84): the live test uses a key *containing*
  `#` (what fixes/000005 broke), the parser test a synthetic `#`-leading
  token.

## `critical` delivery (task 3)
- `Compliance/runtime/python/delivery.py` → `harpia_runtime.delivery`
  (path constant `Compliance.delivery_common.PY_DELIVERY_*`): `crc32`
  (`zlib.crc32`, equal to C++ `detail::crc32`), `Envelope.stamp`/`crc_ok`,
  `Arrival` + `check_on_arrival`, `BoundedQueue` (`queue_rotated` audit on
  overflow), `Mailbox` (`mailbox_overwritten`); caller-synchronized.
- `runtime/zmq_delivery.py` → `harpia_runtime.zmq_delivery`:
  `QueuedSender(Sender)` — `send`/`publish` → `PushOutcome | None`
  (`None` only on an encode failure), seq from 1, envelope kept local;
  `flush()` sends payloads oldest-first, stops at the first `ZMQError`;
  `pending()`, `queue()`. Both modules (+ audit sink) are copied only when a
  `critical` transport message exists.
- A `critical` type's `new_sender`/`new_publisher` return `QueuedSender`
  with extra `queue_capacity=128`, `audit_sink=None` (queue subject = the
  message name, as C++). Receivers unchanged (no arrival checking, as C++).

## Key facts / gotchas
- **Wire = C++ wire:** one serialized-protobuf frame, no envelope. Proven
  by a generated C++ `courier_sender` → Python `new_receiver` test.
- `harpia_runtime.zmq` does `import zmq`; absolute imports mean that is
  pyzmq, not itself.
- **Tear a context with a ZAP handler down with `ctx.term()`, never
  `ctx.destroy()`**: destroy closes the handler's socket from another thread
  and libzmq aborts (seen as a segfault in `test_py_zmq_curve.py`).
- PUB/SUB has the classic slow-joiner: tests publish until the
  subscription is live.

## Touchpoints
- Depends on: `ZmqAdapter.ZmqAdapter` (`_modifiers`, `_origin_id`,
  `_is_one_to_many`), `PyAdapter.runtime_copy`.
- Tested by: `UnitTests/test_py_zmq.py`, `test_py_zmq_curve.py`,
  `test_py_delivery.py`.
