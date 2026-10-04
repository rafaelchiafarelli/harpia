# PySerialization — the Python target's serialization runtimes

**Pipeline role / purpose:** python-target / py-serialization. Hand-written,
message-agnostic Python runtimes, copied into every generated Python project
(`<dest>/python/harpia_runtime/`) by `PySerializationAdapter` (a stage of
`LangBackend/python.py`'s `run_python`). The Python counterparts of
`JsonAdapter/`, `XmlAdapter/runtime/harpia_xml.h`,
`YamlAdapter/runtime/harpia_yaml.h` and `SerializeAdapter/`.

**Entry point:** `PySerializationAdapter(messages, dest, compliance).Process()`
copies each `RUNTIMES` entry (`runtime/<file>` → `harpia_runtime.<module>`)
through `PyAdapter.runtime_copy.copy_runtime_module`. Always returns `None`.

## Runtimes
- `runtime/json.py` → `harpia_runtime.json` (task 1): `to_json(msg)`,
  `from_json(text, msg) -> bool`, `is_valid_json(text, prototype)`.
  `json_format.MessageToDict` + compact `json.dumps`, so the output matches
  C++ `MessageToJsonString` (camelCase, proto3 defaults omitted, int64 as
  strings). `from_json` ignores unknown keys, replaces the message's contents
  like C++ (`ParseFromString` clears), returns `False` and leaves the message
  untouched on failure.

## Key facts / gotchas
- **JSON is byte-identical to C++** for every fixture message (156 types,
  stress strings included; checked 2026-10-04). Plain `json.dumps` differed
  in one way: C++ escapes `<`/`>` as `<`/`>` inside strings.
  `to_json` replaces those two characters, which is safe because they can't
  occur outside a JSON string. Float text could still differ for values the
  two libraries print differently; the stated bar is cross-parse equality.
- Map entries: C++ map iteration order is unspecified, so the parity tests
  populate one entry per map (`UnitTests/_py_cpp_parity.populate`).

## Touchpoints
- Called by: `LangBackend/python.py` (`PythonBackend.run_python`, before the
  docs stage).
- Tested by: `UnitTests/test_py_json.py`, against the C++ runtimes through
  `UnitTests/_py_cpp_parity.py` (one probe binary per generation).
