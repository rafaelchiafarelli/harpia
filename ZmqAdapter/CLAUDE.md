# ZmqAdapter — header-only ZMQ/socket transport (raw-socket alternative to gRPC)

**Pipeline role:** Stage 13 (zmq). For each message with a transport modifier, emits a header-only cppzmq transport that moves the message as a serialized-protobuf frame.
**Entry points (from main.py):** `ZmqAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or `Error` (non-fatal).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash`, `msg.isEnum`, `msg.access_modifiers`, `msg.variables`, `msg.is_critical`). Emits `<dest>/generated/cpp/zmq/<name>_<hash>_zmq.h` ONLY for messages that declare a transport modifier. Enums skipped. When at least one such message is `critical`, also copies the delivery-guarantee runtime into `<dest>/generated/cpp/delivery/` (`harpia_delivery.h` + its `harpia_audit_sink.h` dependency).

## Files
- `ZmqAdapter.py` — `Process()` filters messages by modifier set (`_modifiers` reads `msg.access_modifiers`, each `m[0]`). PUSH/PULL modifiers → sender/receiver pair; EVENT/STREAM → publisher/subscriber pair; messages with neither are skipped. Also computes `_is_one_to_many(mods)` (PULL/EVENT/STREAM present, mirrors `Message.py`'s classification) to pick the sender's default origin id, reads `msg.is_critical` (roadmap Phase 1a) to pick the sender template, and checks `"STREAM" in mods` (`has_stream`) to decide whether to also emit the `<name>_stream` lifecycle consumer. `_render()` assembles the header from sender/receiver/stream template fragments. `_origin_id(md5_hash, name)` is a module-level helper for the compile-time id.
- `templates/header.h.tmpl` — outer header (guard, pb include, `{extra_includes}` + `{stream_includes}` slots, `{stream_shared}` slot, body slot); also defines the shared `CurveServerKeys`/`CurveClientKeys` structs once (own separate include guard, see below). `{extra_includes}` is `""` for a non-critical message (byte-identical to before Phase 3b) and `#include "delivery/harpia_delivery.h"` for a critical one. `{stream_includes}` (`<chrono>`/`<cstddef>`/`<optional>`, file scope) and `{stream_shared}` (`StreamStatus` / `StreamConfig` / `stream_config_valid()`, inside the namespace behind a `HARPIA_ZMQ_STREAM_DEFINED` guard) are both `""` unless the message carries `stream` — an `event`-only or push/pull-only header is byte-identical to before.
- `templates/stream.tmpl` — the `stream`-message consumer lifecycle (zmq-lifecycle epic tasks 1–2, process.md 13.2). Emitted after `<name>_subscriber` only when the message has the `stream` modifier. A per-message `<name>_read_result` (carries a concrete message type) plus `<name>_stream`: `setup(StreamConfig, CurveClientKeys = {})` → `StreamStatus` (INVALID on a bad config, opens nothing); `read()` / `read(int timeout_ms)` → `ReadResult` (`OK`+msg / `TIMEOUT` / `STOPPED` / `INVALID`), always timed via `ZMQ_RCVTIMEO`, never blocking; `stop()` → `STOPPED`, idempotent; RAII destructor closes with `ZMQ_LINGER=0`. Not thread-safe (caller-synchronized, same contract as the delivery runtime). **Two independent time-based teardowns, both synchronous inside `read()`/`stop()`/dtor — no timer thread:** (1) task 1's *stop-deadline watchdog* — `stop_deadline_ms` since the last **usable** message (`last_read_ok_`) → kill + latch INVALID; (2) task 2's *dead-connection reclamation* (`reclaim_if_dead()`) — `reclaim_after_ms` since **any inbound frame** (`last_activity_`, updated on every received frame whether or not it decodes) → kill + latch INVALID. Reclamation is checked first in `read()`, so whichever window is shorter wins; `stop()` runs it too but still returns STOPPED. Defaults: `reclaim_after_ms` 60000 > `stop_deadline_ms` 30000, so a purely idle stream trips the watchdog first; a stream fed garbage frames keeps `last_activity_` fresh but not `last_read_ok_`, so the watchdog is what catches it.
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
  encryption only, not identity.
- **CURVE ZAP client-key allowlist (transport-authn "zmq-zap-allowlist"):**
  when `Crypto.backend.transport_hardening_required(compliance)` is true
  (`self.hardened`), the bind-side (`_CURVE_SERVER_APPLY_ZAP`) socket ctors add
  `::harpia::zap::ensure_running(ctx);` inside the `if (!curve.secret_key.empty())`
  branch, right before `curve_server` is set, and every `*_zmq.h` gains
  `#include "zap/harpia_zap.h"`; `ZmqAdapter` copies `harpia_zap.h` +
  `harpia_audit_sink.h` into `generated/cpp/zap/`. The runtime
  (`ZmqAdapter/runtime/harpia_zap.h`, hand-written like `harpia_grpc_mtls.h`,
  needs cppzmq) runs one `ZapHandler` per `zmq::context_t` -- a REP loop on
  `inproc://zeromq.zap.01` that z85-encodes each CURVE handshake's client key,
  checks it against `AllowList::from_env()` (the `HARPIA_ZMQ_ALLOWLIST` file,
  `<z85-key> <identity>` per line, `#` comments), and answers `200`/`400`.
  Fail-safe: no file / empty file -> deny every key. One value-free `AuditSink`
  `"zap_denied"` record per rejection (z85 key + identity, never secret
  material -- Rule 5). Idempotent: a second `ensure_running` (or a caller's own
  `ZapHandler`) that finds `inproc://zeromq.zap.01` already bound becomes inert
  rather than throwing. Runtime cost is zero unless CURVE is actually
  configured on the socket. Non-hardened output is byte-identical (bar the
  header comment). Path constant: `Compliance/zap_common.py`. Tests:
  `UnitTests/test_zmq_zap.py`; `test_stage13_zmq.py` is pinned to a low-risk
  profile so its CURVE round-trip keeps exercising the encryption-only path.
- **`stream` lifecycle (zmq-lifecycle epic tasks 1–2, process.md 13.2):** a
  message with the `stream` modifier gets a `<name>_stream` class on top of
  its SUB socket, in addition to the unchanged `<name>_subscriber`. It adds
  the spec's explicit consumer lifecycle — `setup()` may reject a config
  with `INVALID`; `read()` is always timed (`TIMEOUT`, never a block);
  `stop()` is idempotent; the destructor releases the socket with
  `ZMQ_LINGER=0`. Two synchronous (no background thread) time-based
  teardowns, both latching `INVALID`: the **stop-deadline watchdog**
  (`stop_deadline_ms` since the last *usable* message) and **dead-connection
  reclamation** (`reclaim_after_ms` since *any* inbound frame — catches a
  connection whose handshake never completed or whose peer vanished, even
  while the caller is still polling). Both run inside `read()` / `stop()` /
  the dtor. `StreamStatus`/`StreamConfig`/`stream_config_valid()` are shared
  per translation unit (`HARPIA_ZMQ_STREAM_DEFINED` guard);
  `<name>_read_result` is per-message. `event`-only messages are untouched
  (no stream surface, byte-identical golden). The `HarpiaTest/Include/
  file3.harpia` fixture for this is `sensor_feed` (`stream`-only, table-less).
- **Origin id / unique sender number (process.md 1.3.1.1):** `_origin_id` = `int(md5(f"{md5_hash}:{name}")[:15], 16)` as a string — a deterministic COMPILE-TIME sender number for the one-to-* (unique publisher) case, used as the sender's default id when `_is_one_to_many(mods)` (PULL/EVENT/STREAM present) is true. When false (only PUSH/PUSHPULL, a shared/many-to-* publisher), the sender's default id instead comes from `runtime_origin_id()` (pid + a per-process counter + random bits, emitted in `templates/header.h.tmpl`) — decentralized, no broker needed. The explicit-origin constructor still exists for a caller-supplied id (e.g. a future broker).
- Sender stamps the origin into the message's `ORIGINATOR` field before sending: `_render` finds the first variable whose name starts with `"ORIGINATOR"` and emits `stamped.set_<field_lower>(origin_)` (protobuf C++ lowercases accessors). No ORIGINATOR field → no stamp line.
- Note the two md5 uses: `msg.md5Hash` (file hash, from ProtoFile) qualifies the filename/pb include; `_origin_id` hashes that hash again with the name for the sender number. Multi-root relevance: both derive from the single per-file hash today.
- Roles/verbs: PUSH sender connects+`send`, PULL receiver binds+`recv`; PUB publisher binds+`publish`, SUB subscriber connects (with `subscribe ""`)+`receive`.
- Pure text emission; headers compile after Stage 7 `.pb.h` exist, over cppzmq. Include root `-I <dest>/generated/cpp`.

## Touchpoints
- Called by: `main.py` (step 13, zmq path — parallel to `GrpcCompiler`/`GrpcServiceAdapter`).
- Depends on: `Util.util.loadTemplate`/`write_if_different`/`copy_if_different`, `Logger.logger`, `Errors.Error`, `hashlib`, and `Compliance.delivery_common` (`DELIVERY_RUNTIME`/`_SRC`/`_DEPS`, for the critical-message runtime copy). Consumes `MessageCreator` messages; runtime depends on cppzmq + protobuf, plus `harpia::delivery`/`harpia::compliance` (header-only) for a critical transport.
