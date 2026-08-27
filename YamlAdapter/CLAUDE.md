# YamlAdapter — reflection-based YAML runtime + per-message wrapper headers

**Pipeline role:** Stage 10 (alongside `XmlAdapter`). Ships a generic reflection-based YAML runtime and emits a thin per-message wrapper so YAML mirrors the JSON/XML adapter shape. Added by Track F / Session F.1 (`Initiatives/medical_devices/epics/thread-3-message-behavior/histories/serialization/`).
**Entry points (from main.py):** `YamlAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or `Error` (non-fatal; `NOTHING_TO_REPORT` when there are no messages).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash`, `msg.isEnum`). Emits `<dest>/generated/cpp/yaml/<name>_<hash>_yaml.h` (wrappers) plus a copy of the runtime `harpia_yaml.h`. Enums skipped.

## Files
- `YamlAdapter.py` — `Process()` copies `runtime/harpia_yaml.h` into the out dir (`copy_if_different`), then renders one wrapper header per non-enum message. `_render()` formats the wrapper with `guard=HARPIA_YAML_<NAME_UPPER>_<hash>`, `pb_header=protofiles/<name>_<hash>.pb.h`, `name`. Same structure as `XmlAdapter.py`.
- `templates/wrapper.h.tmpl` — thin per-message header: `#include`s `yaml/harpia_yaml.h` + the message's `.pb.h`. It exposes **no** per-message symbols — `to_yaml`/`from_yaml` are the generic runtime's, taking a `::google::protobuf::Message&`. The wrapper exists only to pull the two headers in together, matching the JSON/XML per-message shape.
- `runtime/harpia_yaml.h` — the actual YAML engine (hand-written, NOT generated), copied verbatim into every build. Walks any protobuf message via the descriptor/reflection API — nested messages, repeated fields, enums and maps handled generically, no per-field code. Provides `harpia::yaml::to_yaml(msg)` and `from_yaml(yaml, &msg)`.

## Key facts / gotchas
- **Protobuf has no built-in YAML** (like XML, unlike JSON) → the runtime does a reflection walk, mirroring `XmlAdapter/runtime/harpia_xml.h` closely (same `FieldDescriptor::name()` direct-init-by-value trick for the `std::string` vs `std::string_view` return-type split across protobuf versions; same `#undef GetMessage` Windows guard).
- **Emitted shape:** block style, two-space indent, **top-level mapping with no wrapper key** — mirrors the JSON adapter's data model, *not* XML's `<TypeName>` root element. Strings are always double-quoted (escaping `\ " \n \t`); ints/floats/bools/enum-names are bare. `key: {}` / `key: []` for an empty singular message / empty repeated field. Repeated messages use a block sequence of mappings (`- ` + first field inline, continuation fields aligned two columns in).
- **Presence rule matches `harpia_xml.h`:** a field with real presence (a singular message field — always, in proto3; or a scalar the `.harpia` schema marked `optional`) is emitted only when `HasField` is true; an ordinary proto3 scalar is always emitted with its default so the structure/keys are never missing.
- **`from_yaml` parses exactly the subset `to_yaml` emits** — an indentation-driven recursive descent over pre-tokenized lines (blank/`---`/`...` lines dropped). It is **not** a general YAML parser (no flow style beyond `{}`/`[]`, no anchors, no multi-doc, no block scalars). It returns `false` only as a "this text matched none of the message's fields" signal (mirrors `from_xml`'s parse-fail `false`); an empty document or `{}` is a valid empty message → `true`.
- **Maps** are handled generically as protobuf `MapEntry` repeated messages (`refl->AddMessage` on the map field to populate, `GetRepeatedMessage` to read) — same technique protobuf's own JSON/TextFormat parsers use. Emitted as a nested `key: value` mapping under the field name.
- **F.1 scope:** output parity only. No `phi` redaction yet (F.3); JSON/XML/YAML `toString` are still three separate code paths (unified in F.2).
- md5-hash-qualified filenames (`<name>_<hash>`), same scheme as ProtoFile/JsonAdapter/XmlAdapter — multi-root relevance.
- The runtime header is **not** re-snapshotted as golden (same convention as `harpia_xml.h`): it lives here in the repo, `run_pipeline.py`'s `_collect_yaml` copies only the per-message wrappers into `UnitTests/golden/yaml/`.

## Touchpoints
- Called by: `main.py` (step 10, right after `XmlAdapter`), `UnitTests/run_pipeline.py`.
- Depends on: `Util.util.loadTemplate`/`write_if_different`/`copy_if_different`, `Logger.logger`, `Errors.Error`; the runtime depends only on protobuf descriptor/reflection headers (no vendored lib — unlike XML's tinyxml2). Consumes `MessageCreator` messages; pairs with ProtoFile `.pb.h`.
- Tested by: `UnitTests/test_stage10_yaml.py` (protoc+g+++pkg-config-gated: every wrapper compiles + a to_yaml write check + flat / nested-repeated / map round-trips) and `UnitTests/test_golden.py::test_yaml_adapters` (pure-Python wrapper snapshot).
