## HarpiaXml.toXml writes the C++ bytes

- **Depends on:** nothing.
- **Deliverable:** `JavaXmlAdapter/runtime/HarpiaXml.java` writes XML with
  the C++ conventions instead of the DOM `Transformer`: a small string writer
  (or a post-pass) that emits `<x></x>` for empty elements, escapes `& < > " '`
  exactly as `harpia_xml.h` does, and formats floats/doubles like
  `std::to_string` (`String.format(Locale.ROOT, "%f", v)`). Read side
  unchanged.
- **Golden move:** `UnitTests/golden_java/`.
- **Tests:** `test_serialize_xlang3.py` — empty `JAVA_XML_DIFFERENCES` and
  assert Java == C++ bytes; `test_java_xml.py` round trips still pass.
