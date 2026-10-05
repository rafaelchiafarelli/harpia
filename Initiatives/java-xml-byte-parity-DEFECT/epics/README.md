# java-xml-byte-parity-DEFECT — epics

One epic: **`java-xml-parity`**.

```
1-xml-writer-matches-cpp
        │
        ▼
2-compact-json   (optional; Rafael decides at planning)
```

## Definition of done

- `test_serialize_xlang3.py`: `JAVA_XML_DIFFERENCES` (and, with task 2,
  `JSON_BYTE_DIFFERENCES`) emptied; Java == C++ byte for byte over the fixture.
- `golden_java/` diffs reviewed.
- Java SOAP / REST tests still green; full Docker suite green before merging
  up to `dev`.
