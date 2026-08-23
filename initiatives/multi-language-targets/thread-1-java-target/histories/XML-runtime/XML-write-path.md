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