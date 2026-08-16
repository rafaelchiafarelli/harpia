# ZmqAdapter — header-only ZMQ/socket transport (raw-socket alternative to gRPC)

**Pipeline role:** Stage 13 (zmq). For each message with a transport modifier, emits a header-only cppzmq transport that moves the message as a serialized-protobuf frame.
**Entry points (from main.py):** `ZmqAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or `Error` (non-fatal).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash`, `msg.isEnum`, `msg.access_modifiers`, `msg.variables`). Emits `<dest>/generated/cpp/zmq/<name>_<hash>_zmq.h` ONLY for messages that declare a transport modifier. Enums skipped.

## Files
- `ZmqAdapter.py` — `Process()` filters messages by modifier set (`_modifiers` reads `msg.access_modifiers`, each `m[0]`). PUSH/PULL modifiers → sender/receiver pair; EVENT/STREAM → publisher/subscriber pair; messages with neither are skipped. Also computes `_is_one_to_many(mods)` (PULL/EVENT/STREAM present, mirrors `Message.py`'s classification) to pick the sender's default origin id. `_render()` assembles the header from sender/receiver template fragments. `_origin_id(md5_hash, name)` is a module-level helper for the compile-time id.
- `templates/header.h.tmpl` — outer header (guard, pb include, body slot); also defines the shared `CurveServerKeys`/`CurveClientKeys` structs once (own separate include guard, see below).
- `templates/sender.tmpl` — PUSH (`connect`, `send`) / PUB (`bind`, `publish`) socket class; stamps origin id.
- `templates/receiver.tmpl` — PULL (`bind`, `recv`) / SUB (`connect`+subscribe, `receive`) socket class.

## Key facts / gotchas
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
- Depends on: `Util.util.loadTemplate`, `Logger.logger`, `Errors.Error`, `hashlib`. Consumes `MessageCreator` messages; runtime depends on cppzmq + protobuf.
