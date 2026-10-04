## JSON runtime (protobuf `json_format`, C++-equivalent options)

- **Depends on:** `py-foundation` (all).
- **Contract:** `harpia_runtime/json.py`. One message-agnostic module, no
  per-message wrapper; same reasoning as `JavaJsonAdapter/CLAUDE.md`.
  - `to_json(msg) -> str` matches the C++ `MessageToJsonString` defaults:
    camelCase names, proto3 defaults omitted, int64 as strings, **compact**
    separators (`{"a":1}`, not Python's `{"a": 1}`). Built on
    `json_format.MessageToDict` + `json.dumps(separators=(",", ":"))`,
    since `MessageToJson` can't produce compact output.
  - `from_json(text, msg) -> bool` uses `ignore_unknown_fields=True` (the
    message-versioning parse-boundary rule, `JsonAdapter/CLAUDE.md`).
    Returns `False` on a parse failure instead of raising, matching C++'s
    bool return.
  - `is_valid_json(text, prototype) -> bool` never mutates `prototype`.
- **Bar:** cross-parse equality, not byte identity.
  - C++ `to_json` output parsed by Python gives a message equal to the
    original, and vice versa, for every fixture message.
  - Byte identity is checked where it holds and disclosed where it can't:
    float/double text formatting (protobuf C++ vs Python shortest-repr)
    may legitimately differ. Record what was found.
- **Out of scope:** XML/YAML (tasks 2/3), redaction (task 4).
- **Tests:**
  - Unit tests: unknown keys tolerated, defaults omitted, int64-as-string.
  - A protoc+g++-gated cross-check that builds a tiny C++ probe emitting
    `to_json` for a populated fixture message (the `test_stage9.py` build
    shape) and asserts the two-way parse equality above.
