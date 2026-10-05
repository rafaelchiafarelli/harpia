# Java XML is not byte-identical to C++/Python — DEFECT

**Status: scoped, not started.** Found 2026-10-04 (python-target
`tri-language-interop/4`; decisions log item 47 in
`Initiatives/python-target/NEXT_SESSION.md`). Not fixed: it moves
`golden_java/` and changes Java's wire text.

## What was found

`UnitTests/test_serialize_xlang3.py` compares `HarpiaXml.toXml`
(`JavaXmlAdapter/runtime/HarpiaXml.java`) with the C++ `harpia_xml.h` /
Python `harpia_runtime.xml` output over the whole fixture. The documents
parse to the same message in every direction; the bytes differ in exactly
three ways (pinned there as `JAVA_XML_DIFFERENCES`):

1. **Empty elements** — Java `<x/>` (DOM `Transformer`, ~line 197), C++
   `<x></x>`.
2. **Quotes in text** — Java writes `"` and `'` raw, C++ escapes them
   (`&quot;` / `&apos;`).
3. **Float text** — Java `String.valueOf(value)` (~line 94: `0.0`, `15.25`),
   C++ `std::to_string` / `%f` (`0.000000`, `15.250000`).

Java JSON (`HarpiaJson`, `JsonFormat.printer()`) differs from C++ only in
whitespace (pretty printer); the objects are equal. Optional cleanup:
`.omittingInsignificantWhitespace()` would make it byte-identical too.

Matters for anything that signs, hashes, caches or diffs the XML text across
languages (e.g. SOAP envelopes compared byte for byte).

## Scope

One epic: **`java-xml-parity`**. **Moves `UnitTests/golden_java/`** and
changes Java's XML/JSON text (not its meaning). See `epics/README.md`.
