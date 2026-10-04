## XML runtime — byte-identical port of `harpia_xml.h`

- **Depends on:** task 1 (module layout precedent only).
- **Contract:** `harpia_runtime/xml.py`. A reflection walk over
  `msg.DESCRIPTOR`, a line-for-line port of
  `XmlAdapter/runtime/harpia_xml.h`. It provides `to_xml(msg) -> str`,
  `from_xml(text, msg) -> bool`, `from_xml_element(element, msg) -> bool`
  (for SOAP/dbio) and `xsd(descriptor) -> str`. **Python includes XSD;
  Java skipped it.**
  - Root element is the message **type name**.
  - Presence rule (`XmlAdapter/CLAUDE.md`): a field with real presence is
    emitted only when set; an ordinary proto3 scalar is always emitted.
  - Nested messages, repeated fields, enums (by name) and maps
    (`MapEntry`) are handled generically.
  - Escaping identical to `detail::escape`.
  - Numbers formatted exactly like C++ `std::to_string`: integers plain,
    float/double as `"%f"` (six decimals). A Python float read from a
    proto `float` field is already the float32 value widened, which is
    what `std::to_string(float)` prints.
  - Parsing uses stdlib `xml.etree.ElementTree`. Emission is hand-built
    (not ElementTree's serializer), because the C++ emitter is hand-built
    string concatenation too, and byte parity with it is the bar.
- **Bar:** `to_xml` output is **byte-identical** to the C++ runtime for
  every fixture message (`HarpiaTest/test.harpia` + `Include/`), including
  nested, repeated, map, enum and `optional`-presence cases. `from_xml` of
  C++ output equals the original message.
- **Out of scope:** the SOAP envelope (`py-transports-http` task 3), dbio
  (`py-database` task 6).
- **Tests:**
  - Unit round-trips per shape.
  - A protoc+g++-gated byte-parity test against a C++ probe (the
    `test_stage10_xml.py` build shape) over every fixture message
    populated with deterministic values.
  - `xsd()` compared to the C++ `xsd()` for one nested message.
