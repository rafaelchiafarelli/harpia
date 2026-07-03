# ZmqAdapter — header-only ZMQ/socket transport (raw-socket alternative to gRPC)

**Pipeline role:** Stage 13 (zmq). For each message with a transport modifier, emits a header-only cppzmq transport that moves the message as a serialized-protobuf frame.
**Entry points (from main.py):** `ZmqAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or `Error` (non-fatal).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash`, `msg.isEnum`, `msg.access_modifiers`, `msg.variables`). Emits `<dest>/generated/cpp/zmq/<name>_<hash>_zmq.h` ONLY for messages that declare a transport modifier. Enums skipped.

## Files
- `ZmqAdapter.py` — `Process()` filters messages by modifier set (`_modifiers` reads `msg.access_modifiers`, each `m[0]`). PUSH/PULL modifiers → sender/receiver pair; EVENT/STREAM → publisher/subscriber pair; messages with neither are skipped. `_render()` assembles the header from sender/receiver template fragments. `_origin_id(md5_hash, name)` is a module-level helper.
- `templates/header.h.tmpl` — outer header (guard, pb include, body slot).
- `templates/sender.tmpl` — PUSH (`connect`, `send`) / PUB (`bind`, `publish`) socket class; stamps origin id.
- `templates/receiver.tmpl` — PULL (`bind`, `recv`) / SUB (`connect`+subscribe, `receive`) socket class.

## Key facts / gotchas
- **Origin id / unique sender number (process.md 1.3.1.1):** `_origin_id` = `int(md5(f"{md5_hash}:{name}")[:15], 16)` as a string — a deterministic COMPILE-TIME sender number for the one-to-* (unique publisher) case. Many-to-* (shared publisher, runtime-assigned id via a broker) is future work; the alternate constructor entry point exists but the broker doesn't.
- Sender stamps the origin into the message's `ORIGINATOR` field before sending: `_render` finds the first variable whose name starts with `"ORIGINATOR"` and emits `stamped.set_<field_lower>(origin_)` (protobuf C++ lowercases accessors). No ORIGINATOR field → no stamp line.
- Note the two md5 uses: `msg.md5Hash` (file hash, from ProtoFile) qualifies the filename/pb include; `_origin_id` hashes that hash again with the name for the sender number. Multi-root relevance: both derive from the single per-file hash today.
- Roles/verbs: PUSH sender connects+`send`, PULL receiver binds+`recv`; PUB publisher binds+`publish`, SUB subscriber connects (with `subscribe ""`)+`receive`.
- Pure text emission; headers compile after Stage 7 `.pb.h` exist, over cppzmq. Include root `-I <dest>/generated/cpp`.

## Touchpoints
- Called by: `main.py` (step 13, zmq path — parallel to `GrpcCompiler`/`GrpcServiceAdapter`).
- Depends on: `Util.util.loadTemplate`, `Logger.logger`, `Errors.Error`, `hashlib`. Consumes `MessageCreator` messages; runtime depends on cppzmq + protobuf.
