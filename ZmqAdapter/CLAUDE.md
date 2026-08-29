# ZmqAdapter — header-only ZMQ/socket transport (raw-socket alternative to gRPC)

**Pipeline role:** Stage 13 (zmq). For each message with a transport modifier, emits a header-only cppzmq transport that moves the message as a serialized-protobuf frame.
**Entry points (from main.py):** `ZmqAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or `Error` (non-fatal).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash`, `msg.isEnum`, `msg.access_modifiers`, `msg.variables`, `msg.is_critical`). Emits `<dest>/generated/cpp/zmq/<name>_<hash>_zmq.h` ONLY for messages that declare a transport modifier. Enums skipped. When at least one such message is `critical`, also copies the delivery-guarantee runtime into `<dest>/generated/cpp/delivery/` (`harpia_delivery.h` + its `harpia_audit_sink.h` dependency).

## Files
- `ZmqAdapter.py` — `Process()` filters messages by modifier set (`_modifiers` reads `msg.access_modifiers`, each `m[0]`). PUSH/PULL modifiers → sender/receiver pair; EVENT/STREAM → publisher/subscriber pair; messages with neither are skipped. Also computes `_is_one_to_many(mods)` (PULL/EVENT/STREAM present, mirrors `Message.py`'s classification) to pick the sender's default origin id, and reads `msg.is_critical` (roadmap Phase 1a) to pick the sender template. `_render()` assembles the header from sender/receiver template fragments. `_origin_id(md5_hash, name)` is a module-level helper for the compile-time id.
- `templates/header.h.tmpl` — outer header (guard, pb include, `{extra_includes}` slot, body slot); also defines the shared `CurveServerKeys`/`CurveClientKeys` structs once (own separate include guard, see below). `{extra_includes}` is `""` for a non-critical message (byte-identical to before Phase 3b) and `#include "delivery/harpia_delivery.h"` for a critical one.
- `templates/sender.tmpl` — non-critical PUSH (`connect`, `send`) / PUB (`bind`, `publish`) socket class; `send`/`publish` returns `bool`, fires the socket directly; stamps origin id.
- `templates/sender_critical.tmpl` — the `critical`-message sender/publisher (roadmap Phase 3b). Same origin-id / CURVE / stamp shape as `sender.tmpl`, but `send`/`publish` returns `::std::optional<::harpia::delivery::PushOutcome>` and *enqueues* a CRC+seq-stamped `harpia::delivery::Envelope` into a member `BoundedQueue` instead of touching the socket; a separate `flush()` drains the queue to the wire oldest-first, stopping at the first socket failure (transient outage → latency, not loss). Ctor gains `queue_capacity` (default 128) and `AuditSink&` (default `default_audit_sink()`) params, before the trailing CURVE-keys param. Extra accessors: `pending()`, `queue()`.
- `templates/receiver.tmpl` — PULL (`bind`, `recv`) / SUB (`connect`+subscribe, `receive`) socket class. Unchanged by Phase 3b — the receiving half of a `critical` type is not queued (arrival-side `check_on_arrival` is a Phase 3c concern).

## Key facts / gotchas
- **`critical` send path (roadmap Phase 3b, design-rules Rule 4a):** a
  `critical` message type's sender/publisher routes through
  `harpia::delivery::BoundedQueue` — `send()`/`publish()` stamps an
  `Envelope` (origin CRC-32 + per-sender monotonic `next_seq_`, starting at
  1) and pushes it; the queue rotates its oldest entry on overflow with a
  `"queue_rotated"` `AuditSink` record (never a silent drop); `flush()` is
  what actually puts bytes on the socket. Non-`critical` types keep the
  direct `bool send()` API, byte-for-byte unchanged (golden regen touched
  only `alarm_event`'s header). The delivery runtime is copied to a shared
  `generated/cpp/delivery/` (mirrors the capability runtime's
  `generated/cpp/capability/` home) and only when a critical transport
  message actually exists — a project with none gets no new directory.
  `Compliance.delivery_common` supplies the source paths
  (`DELIVERY_RUNTIME_SRC` + `DELIVERY_RUNTIME_DEPS`, the latter naming
  `harpia_audit_sink.h` as a co-copy since the delivery header `#include`s
  it at the same relative path). This is the C++ target only — `JavaZmqAdapter`
  does not read `is_critical` yet.
- **CURVE encryption (encryption-only, no ZAP allowlist):** every generated
  constructor takes a trailing, defaulted curve-keys struct
  (`CurveServerKeys{secret_key}` for the bind side -- PULL receiver / PUB
  publisher; `CurveClientKeys{server_public_key, public_key, secret_key}`
  for the connect side -- PUSH sender / SUB subscriber), defined once per
  header behind their own `HARPIA_ZMQ_CURVE_KEYS_DEFINED` guard (separate
  from the per-message `{guard}`) so they don't collide when several
  `*_zmq.h` land in one translation unit. An empty/default struct is a no-op
  -- callers who pass nothing get today's plaintext behavior, byte-identical
  except for the added constructor text (golden fixtures needed a regen for
  this). `_render()` picks the struct type + apply-code per role
  (`_CURVE_SERVER_APPLY`/`_CURVE_CLIENT_APPLY`), the same way it already
  varies `connect=`/`setup=` per role. See `USAGE.md` §10 for the demo
  wiring (`Assets/CMakeLists.txt`'s keygen probe) and the `ZMQ_LINGER`
  gotcha (a socket with an undelivered message from a failed handshake
  blocks on destruction forever unless linger is set to 0). This is
  encryption only, not identity -- ZAP client-key allowlisting (mTLS's
  analogue) was explicitly out of scope.
- **Origin id / unique sender number (process.md 1.3.1.1):** `_origin_id` = `int(md5(f"{md5_hash}:{name}")[:15], 16)` as a string — a deterministic COMPILE-TIME sender number for the one-to-* (unique publisher) case, used as the sender's default id when `_is_one_to_many(mods)` (PULL/EVENT/STREAM present) is true. When false (only PUSH/PUSHPULL, a shared/many-to-* publisher), the sender's default id instead comes from `runtime_origin_id()` (pid + a per-process counter + random bits, emitted in `templates/header.h.tmpl`) — decentralized, no broker needed. The explicit-origin constructor still exists for a caller-supplied id (e.g. a future broker).
- Sender stamps the origin into the message's `ORIGINATOR` field before sending: `_render` finds the first variable whose name starts with `"ORIGINATOR"` and emits `stamped.set_<field_lower>(origin_)` (protobuf C++ lowercases accessors). No ORIGINATOR field → no stamp line.
- Note the two md5 uses: `msg.md5Hash` (file hash, from ProtoFile) qualifies the filename/pb include; `_origin_id` hashes that hash again with the name for the sender number. Multi-root relevance: both derive from the single per-file hash today.
- Roles/verbs: PUSH sender connects+`send`, PULL receiver binds+`recv`; PUB publisher binds+`publish`, SUB subscriber connects (with `subscribe ""`)+`receive`.
- Pure text emission; headers compile after Stage 7 `.pb.h` exist, over cppzmq. Include root `-I <dest>/generated/cpp`.

## Touchpoints
- Called by: `main.py` (step 13, zmq path — parallel to `GrpcCompiler`/`GrpcServiceAdapter`).
- Depends on: `Util.util.loadTemplate`/`write_if_different`/`copy_if_different`, `Logger.logger`, `Errors.Error`, `hashlib`, and `Compliance.delivery_common` (`DELIVERY_RUNTIME`/`_SRC`/`_DEPS`, for the critical-message runtime copy). Consumes `MessageCreator` messages; runtime depends on cppzmq + protobuf, plus `harpia::delivery`/`harpia::compliance` (header-only) for a critical transport.
