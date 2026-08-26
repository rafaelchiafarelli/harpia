# JavaXmlAdapter — Java target: reflection-based XML runtime (one shared class, no per-message generation)

**Pipeline role:** Java-target Stage 10 equivalent (sessions J.10 write path / J.11 read path, `initiatives/multi-language-targets/thread-1-java-target`). Ships a single hand-written, reflection-based XML runtime class, directly comparable in shape to the C++ target's `XmlAdapter/runtime/harpia_xml.h` — read that file first, this is a deliberate line-for-line port of its walking logic onto protobuf-java's reflection API.
**Entry point (from main.py):** gated behind `HARPIA_GEN_LANG=java`, called right after `JavaDatabase`'s two adapters in the same block: `JavaXmlAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()`. Returns `None` or an `Error` (non-fatal; main.py logs it).
**Inputs → Outputs:** consumes message objects only to decide whether there's anything to generate for (same as `JavaJsonAdapter`) — the runtime class itself is message-agnostic. Emits exactly one file: `<dest>/java/src/main/java/com/harpia/runtime/xml/HarpiaXml.java`.

## Files
- `JavaXmlAdapter.py` — `Process()` copies (`copy_if_different`) `runtime/HarpiaXml.java` in. No per-message loop.
- `runtime/HarpiaXml.java` — hand-written (NOT generated), copied verbatim. `toXml(Message)` / `fromXml(String, Message.Builder)` (J.11), walking any message via `Descriptors.FieldDescriptor` + `Message.getField(fd)`/`hasField(fd)`/`getRepeatedField(fd, k)`/`getRepeatedFieldCount(fd)` — handles nested messages, repeated fields and enums generically, no per-message/per-field generated code, same as the C++ runtime. Uses `javax.xml`'s DOM (`DocumentBuilderFactory`/`Document`/`Transformer`) — **JDK-builtin, zero extra dependency**, genuinely cheaper than C++'s story (which had to vendor `tinyxml2`, since protobuf has no built-in XML support in either language). DOM's own serializer handles XML-escaping automatically (`&`/`<`/`>`/etc. in text content) — no hand-rolled `escape()` helper needed, unlike the C++ runtime's own `detail::escape()`.

## Depends on the full protobuf-java runtime, not `protobuf-javalite`
This runtime's whole approach (walking `Descriptors.FieldDescriptor` via
reflection) is impossible against `javalite`-generated classes, which
have no reflection API at all. See `JavaJsonAdapter/CLAUDE.md`'s "Why the
full protobuf-java runtime" section for the full decision record (also
covers JSON, which depends on the same choice) — resolved in favor of the
full runtime, confirmed against a real Android build's DEX/multidex
behavior.

## Why no per-message wrapper (same reasoning as JavaJsonAdapter)
C++'s `XmlAdapter` still emits a thin per-message wrapper header (`<name>_xml.h`) around the shared `harpia_xml.h` runtime, explicitly "so XML mirrors the JSON adapter shape" (`XmlAdapter/CLAUDE.md`) — a typed-call ergonomics choice, not a technical requirement of the underlying reflection walk (which is already generic over any `google::protobuf::Message`). In Java, every generated message class already implements the common `Message` interface, so `HarpiaXml.toXml(msg)`/`HarpiaXml.fromXml(xml, builder)` already work polymorphically for any message type — see `JavaJsonAdapter/CLAUDE.md` for the fuller version of this argument, first made there for JSON.

## Presence gating (why it matters, ported faithfully)
`writeMessage()` emits a singular field only when `fd.hasPresence() && !msg.hasField(fd)` is false — i.e. skips it when the field HAS presence but ISN'T set. `hasPresence()` is true for: any singular **message** field (always has presence in proto3 — an absent one must round-trip as absent, not as a phantom present-with-defaults child, e.g. a spurious FK row); a scalar explicitly marked `optional` in the `.harpia` schema (message-versioning effort's parse-boundary hardening, `protoFile/CLAUDE.md`'s `optional` note — the exact "explicitly 0" vs "never set" ambiguity presence tracking exists to close). An ordinary (non-`optional`) proto3 scalar has no presence to track and is always emitted with its default — `fd.hasPresence()` is false for those, so the check short-circuits without ever calling `hasField()` on a field that doesn't support it (protobuf-java's `hasField()` throws for a field with no presence). This is the exact same rule, same reason, same short-circuit-before-calling-hasField discipline as the C++ runtime's own `if (f->has_presence() && !refl->HasField(msg, f)) continue;` — see `XmlAdapter/CLAUDE.md`'s own gotcha entry for the C++ side of this.

## Key facts / gotchas
- **No XSD generation** (unlike the C++ runtime's `xsd()`) — not in J.10/J.11's scoped deliverables, not itemized elsewhere in the Java target's session breakdown either (`../initiatives/multi-language-targets/thread-1-java-target/README.md`). Flagged, not silently assumed to be covered.
- Root XML element is the message's **type name** (`msg.getDescriptorForType().getName()`), matching the C++ runtime (`msg.GetDescriptor()->name()`).
- Repeated composed fields to a table-less message (e.g. `shipment.cargo` → `parcel`, deferred entirely by `JavaDatabase`'s CRUDL scope, see its `CLAUDE.md`) serialize to XML with **no special casing at all** — XML doesn't need SQL columns, so the DB-layer scope reduction doesn't limit this runtime in any way. A good illustration that the two stages' "hard cases" don't actually overlap.
- `fromXml` (J.11) returns `false` on a parse failure rather than throwing, matching the C++ runtime's `bool` return and the repo-wide convention (`is_valid_json`-style) of a boolean outcome for "did this parse," not an exception.

## Touchpoints
- Called by: `main.py`, gated on `HARPIA_GEN_LANG=java`, right after `JavaDatabase`'s two adapters in the same conditional block.
- Depends on: `Util.util.copy_if_different`, `Logger.logger`, `Errors.Error`. The runtime class itself depends only on `protobuf-java` (already a `build.gradle` dependency since J.2) and JDK-builtin `javax.xml`/`org.w3c.dom` — no new Gradle dependency for this session at all.
