# SerializeAdapter — unified JSON/XML/YAML `toString` façade

**Pipeline role:** Stage 10 (after `YamlAdapter`). Added by Track F / Session F.2 ("close out the JSON/XML/YAML `toString` triad through one shared path"). Ships one runtime header + a thin per-message wrapper, same shape as the JSON/XML/YAML adapters.
**Entry points (from main.py):** `SerializeAdapter(messages=msgFactory.messages, dest=testDestination).Process()`. Returns `None` or `Error` (`NOTHING_TO_REPORT` when there are no messages).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash`, `msg.isEnum`). Emits `<dest>/generated/cpp/serialize/<name>_<hash>_serialize.h` (wrappers) plus a copy of the runtime `harpia_serialize.h`. Enums skipped.

## Files
- `SerializeAdapter.py` — `Process()` copies `runtime/harpia_serialize.h` into the out dir, then renders one wrapper per non-enum message. Same structure as `YamlAdapter.py`.
- `templates/wrapper.h.tmpl` — thin per-message header: `#include`s `serialize/harpia_serialize.h` + the message's `.pb.h`. No per-message symbols — `to_string`/`from_string` are the generic runtime's, taking a `::google::protobuf::Message&`.
- `runtime/harpia_serialize.h` — the façade (hand-written, NOT generated). `harpia::serialize::Format{JSON,XML,YAML}`, `to_string(const Message&, Format)`, `from_string(const std::string&, Message*, Format)`, `format_name(Format)`.

## Key facts / gotchas
- **It is a dispatch layer, not a re-implementation.** JSON → protobuf's own `MessageToJsonString` / `JsonStringToMessage` (default options: camelCase keys, proto3 defaults omitted, `ignore_unknown_fields=true` on parse — identical to what `json/<name>_json.h` does). XML → `::harpia::xml::to_xml` / `from_xml`. YAML → `::harpia::yaml::to_yaml` / `from_yaml`. So JSON and XML output stay **byte-for-byte** what they already were — that is the F.2 acceptance gate (existing `json/`/`xml/` golden snapshots unchanged for non-`phi` messages), and `test_stage10_serialize.py::test_json_path_is_behavior_preserving` asserts the JSON parity directly.
- **The three formats do NOT share a structural convention** and this façade does not try to unify that — protobuf-JSON is camelCase + defaults-omitted, the XML/YAML reflection walkers are snake_case + defaults-always-present. "One shared path" means one API / one dispatch point (and, from F.3 on, one place `phi` redaction hooks), not one output shape. Round-trip tests assert `SerializeAsString()` equality per format, never cross-format text equality.
- **`phi` redaction (F.3) hooks here, once.** F.2 itself adds no redaction — `to_string` is a straight pass-through to the engines.
- `#include`s `xml/harpia_xml.h` and `yaml/harpia_yaml.h` by their in-build relative paths, so a TU that includes a `serialize/` wrapper needs `-I <cpp_root>` and (because `harpia_xml.h` pulls in tinyxml2) `-I third_party/tinyxml2`.
- md5-hash-qualified wrapper filenames, same scheme as the sibling adapters.
- The runtime header is **not** golden-snapshotted (same convention as `harpia_xml.h`/`harpia_yaml.h`): `run_pipeline.py`'s `_collect_serialize` copies only the per-message wrappers into `UnitTests/golden/serialize/`.

## Touchpoints
- Called by: `main.py` (step 10, right after `YamlAdapter`), `UnitTests/run_pipeline.py`.
- Depends on: `Util.util` (`loadTemplate`/`write_if_different`/`copy_if_different`), `Logger.logger`, `Errors.Error`; the runtime depends on protobuf (`message.h`, `util/json_util.h`) + the XML/YAML runtimes it dispatches to. Consumes `MessageCreator` messages; pairs with ProtoFile `.pb.h`.
- Tested by: `UnitTests/test_stage10_serialize.py` (protoc+g+++pkg-config-gated: every wrapper compiles; flat + nested/repeated round-trips through all three formats; JSON byte-parity with protobuf util and the existing `json/` wrapper; default/odd-string robustness) and `UnitTests/test_golden.py::test_serialize_adapters`.
