# XmlAdapter — reflection-based XML runtime + per-message wrapper headers

**Pipeline role:** Stage 10. Ships a generic reflection-based XML runtime and emits a thin per-message wrapper so XML mirrors the JSON adapter shape.
**Entry points (from main.py):** `XmlAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or `Error` (non-fatal).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash`, `msg.isEnum`). Emits `<dest>/generated/cpp/xml/<name>_<hash>_xml.h` (wrappers) plus a copy of the runtime `harpia_xml.h`. Enums skipped.

## Files
- `XmlAdapter.py` — `Process()` copies `runtime/harpia_xml.h` into the out dir (via `shutil.copy2`), then renders one wrapper header per message. `_render()` formats the wrapper with `guard=HARPIA_XML_<NAME_UPPER>_<hash>`, `pb_header=protofiles/<name>_<hash>.pb.h`, `name`.
- `templates/wrapper.h.tmpl` — thin per-message header; exposes `harpia::xml::to_xml`, `from_xml`, `xsd` bound to the message type.
- `runtime/harpia_xml.h` — the actual XML engine (hand-written, NOT generated), copied verbatim into every build. Walks any protobuf message via the descriptor/reflection API — handles nested messages, repeated fields, enums, maps generically. Provides `to_xml`, `from_xml`, `from_xml_element` (batch import), and `xsd(descriptor)` schema generation. Uses vendored `tinyxml2` for parsing.

## Key facts / gotchas
- Unlike JSON, protobuf has NO built-in XML → the runtime does reflection walking rather than per-field generated code.
- Runtime quirk (important): a singular field is emitted only when `HasField` is true whenever the field has REAL presence (`FieldDescriptor::has_presence()`) — always true for **message** fields (otherwise an absent child would round-trip as an empty *present* child, e.g. making an FK adapter persist a phantom row), and true for a **scalar** field only when the `.harpia` schema marks it `optional` (proto3 explicit presence, added as part of the message-versioning effort's parse-boundary hardening — see `protoFile/CLAUDE.md`). An ordinary (non-`optional`) proto3 scalar has no presence to track and is always emitted with its default.
- `_WRAPPER` template and `_RUNTIME_SRC` path are resolved at import time. Runtime is copied on every `Process()` call.
- Root element in `to_xml` is the message *type name*; XSD collects reachable message types depth-first (cycle-safe).
- **Windows portability (verified, see `USAGE.md` §11):** every `FieldDescriptor::name()`/`Descriptor::name()` result is bound with direct-initialization (`const std::string tag(f->name())`, not `const std::string& tag = f->name()`), because newer protobuf (e.g. vcpkg's) returns `std::string_view` there where older protobuf (e.g. apt's, used by the Docker pipeline) returns `const std::string&` — direct-init compiles against both, a `=`-binding to a reference does not. Also unconditionally `#undef GetMessage` after the includes: `<windows.h>` (pulled in transitively via Crow/asio on Windows) defines `GetMessage` as a macro (`winuser.h`'s `GetMessageA`/`W`), which would otherwise silently rewrite `Reflection::GetMessage()` into a call to a member that doesn't exist.
- md5-hash-qualified filenames (multi-root relevance, same as ProtoFile/JsonAdapter).
- Database-backed XML functions (spec 9.3-9.6) are implemented in `Database/DbIoAdapter.py` (composes `to_xml`/`from_xml` with the CRUDL DAO), not here.

## Touchpoints
- Called by: `main.py` (step 10).
- Depends on: `Util.util.loadTemplate`, `Logger.logger`, `Errors.Error`, `shutil`; the runtime depends on protobuf headers + vendored `tinyxml2`. Consumes `MessageCreator` messages; pairs with ProtoFile `.pb.h`.
