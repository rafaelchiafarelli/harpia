## HarpiaJson prints compact JSON (optional)

- **Depends on:** nothing; planning decision whether to do it at all (Java
  clients may rely on pretty output in logs).
- **Deliverable:** `JsonFormat.printer().omittingInsignificantWhitespace()` in
  `JavaJsonAdapter/runtime/HarpiaJson.java`; confirm escaping (`\u003c` etc.)
  then matches C++.
- **Golden move:** `UnitTests/golden_java/`.
- **Tests:** `test_serialize_xlang3.py` — empty `JSON_BYTE_DIFFERENCES`;
  `test_java_json_pass_through.py` still green.
