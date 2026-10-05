# java-xml-byte-parity-DEFECT — epics

One epic: **`java-xml-parity`**, one task: `1-xml-writer-matches-cpp`.

## Decision (Rafael, 2026-10-05)

Java JSON stays pretty-printed. The objects already equal C++'s; the
whitespace-only byte difference stays pinned in `JSON_BYTE_DIFFERENCES`. The
former optional `2-compact-json` task was dropped.

## Definition of done

- `test_serialize_xlang3.py`: `JAVA_XML_DIFFERENCES` emptied; Java XML == C++
  byte for byte over the fixture.
- `golden_java/` diffs reviewed.
- Java SOAP / REST tests still green; full Docker suite green before merging
  up to `dev`.
