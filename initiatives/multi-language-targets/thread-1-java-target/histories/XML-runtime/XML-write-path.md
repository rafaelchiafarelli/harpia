### Session J.10 — XML write path (`to_xml`)

- **Depends on:** J.2 merged.
- **Deliverable:** a reflection-walking serialization runtime over
  protobuf-java's reflection API (`Message.getDescriptorForType()`,
  `Descriptors.FieldDescriptor`, `Message.getField(fd)`/`hasField(fd)`),
  directly comparable in shape to `harpia_xml.h`. Uses JDK-builtin
  `javax.xml`/DOM/StAX — zero extra dependency, genuinely cheaper here
  than the C++ story (which had to vendor `tinyxml2`).
- **Out of scope:** the read path (J.11).
- **Tests:**
  - Unit: XML serialization for a message with nested/repeated fields,
    presence-gated singular-field emission matching the C++ runtime's
    `has_presence()` behavior (see `XmlAdapter/CLAUDE.md` for why that
    check matters — the C++ runtime gates singular-field emission on
    `HasField` for exactly this reason).

## Implementation notes (landed 2026-08-23, together with J.11)

New `JavaXmlAdapter/runtime/HarpiaXml.java`, a deliberate port of
`XmlAdapter/runtime/harpia_xml.h`'s reflection-walking logic onto
protobuf-java's `Descriptors.FieldDescriptor`/`Message.getField(fd)`/
`hasField(fd)`/`getRepeatedField(fd,k)` API — same structure, same
presence-gating rule (`fd.hasPresence() && !msg.hasField(fd)` skips a
singular field, never calling `hasField()` when presence isn't supported,
which protobuf-java's `hasField()` would reject). `javax.xml`'s DOM is
JDK-builtin — zero extra Gradle dependency, and DOM's own serializer
XML-escapes text content for free (no hand-rolled `escape()` needed,
unlike the C++ runtime's).

**Not per-message generated** (unlike C++'s `XmlAdapter`, which still
emits a thin per-message wrapper "so XML mirrors the JSON adapter shape")
— same reasoning as `JavaJsonAdapter` (J.4): protobuf-java's common
`Message` interface already makes this one class generic over every
message type. Full rationale in `JavaXmlAdapter/CLAUDE.md`.

**No XSD generation** — not scoped in this session's deliverable, not
itemized elsewhere in the 27-session breakdown; flagged rather than
silently assumed covered.

Tests: `tests/test_java_xml.py` (covers J.10 and J.11 together).