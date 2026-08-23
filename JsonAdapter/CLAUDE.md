# JsonAdapter — per-message header-only JSON adapter (wraps protobuf JSON util)

**Pipeline role:** Stage 9. Emits a thin C++ header per message that wraps `google::protobuf::util` JSON support.
**Entry points (from main.py):** `JsonAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or an `Error` (non-fatal; main.py logs it).
**Inputs → Outputs:** consumes message objects (uses `msg.name`, `msg.md5Hash`, `msg.isEnum`). Emits `<dest>/generated/cpp/json/<name>_<hash>_json.h`. Enums are skipped (carried inside messages).

## Files
- `JsonAdapter.py` — `Process()` makes the out dir, loops messages, renders and writes one header each; returns `NOTHING_TO_REPORT` error if nothing written. `_render()` formats the template with: `guard=HARPIA_JSON_<NAME_UPPER>_<hash>`, `pb_header=protofiles/<name>_<hash>.pb.h`, `cls=::<name>`, `name`.
- `templates/adapter.h.tmpl` — the C++ header text (Python `str.format` placeholders). Provides `to_json(msg, *out)`, `from_json(in, *msg)`, `is_valid_json(in)`. `from_json`/`is_valid_json` pass `JsonParseOptions{{ignore_unknown_fields = true}}` to `JsonStringToMessage` (plain single-arg `JsonStringToMessage` defaults that to `false`) so a JSON payload carrying a key this schema doesn't recognize (a newer peer's added field) still parses, matching proto3 binary/XML's own tolerant-unknown-field behavior — see `plans/message-versioning.md` §4.

## Key facts / gotchas
- Template is loaded ONCE at import time via `loadTemplate(__file__, "adapter.h.tmpl")` (module-level constant `_TEMPLATE`).
- Pure text emission — does NOT need `protoc` to have run; the emitted headers only *compile* after Stage 7 produced the `.pb.h` files (inside Docker).
- Includes the generated message header via protoc include root `-I <dest>/generated/cpp`.
- Filenames are md5-hash-qualified (`<name>_<hash>`), same hash scheme as ProtoFile — relevant to multi-root.
- Database-backed JSON functions (spec 8.3-8.6) are implemented in `Database/DbIoAdapter.py` (composes `to_json`/`from_json` with the CRUDL DAO), not here.

## Touchpoints
- Called by: `main.py` (step 9).
- Depends on: `Util.util.loadTemplate`, `Logger.logger`, `Errors.Error`. Consumes `MessageCreator` messages. Downstream output pairs with ProtoFile's `.pb.h`.
