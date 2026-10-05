## HarpiaXml.toXml writes the C++ bytes

- **Depends on:** nothing.
- **1. Corroborate (red first):** add three focused tests to
  `UnitTests/test_java_xml.py`, each comparing Java `toXml` to C++
  `harpia_xml.h` output for one crafted message:
  - `test_java_xml_empty_element_matches_cpp` — empty string field → C++
    `<x></x>`, Java today `<x/>`.
  - `test_java_xml_quotes_escaped_like_cpp` — text with `"` and `'` → C++
    `&quot;` / `&apos;`, Java today raw.
  - `test_java_xml_float_text_matches_cpp` — `0.0f`, `15.25`, a double →
    C++ `0.000000` / `15.250000`, Java today `0.0` / `15.25`.
  All three must **fail** on unmodified code; any that passes means that
  difference class isn't real → drop it from the fix and record it.
- **2. Fix:** `JavaXmlAdapter/runtime/HarpiaXml.java` writes XML with the
  C++ conventions instead of the DOM `Transformer` (~197): a small string
  writer that emits `<x></x>` for empty elements, escapes `& < > " '`
  exactly as `harpia_xml.h`, and formats floats/doubles like
  `std::to_string` (`String.format(Locale.ROOT, "%f", v)`). Read side
  unchanged.
- **3. Unit tests (required, kept):**
  - The three tests above — now green.
  - `test_serialize_xlang3.py::test_xml`: `JAVA_XML_DIFFERENCES` emptied and
    the test asserts Java == C++ bytes over the whole fixture.
  - Existing `test_java_xml.py` round trips stay green (Java parses its own
    new output and the C++ output).
- **Golden move:** `UnitTests/golden_java/`.
