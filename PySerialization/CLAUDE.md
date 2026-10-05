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

- `runtime/reflect.py` → `harpia_runtime.reflect` (task 2): helpers the XML,
  YAML and façade runtimes share — `scalar_text` (C++ `std::to_string`
  printing: `%f` floats, `true`/`false`, enum names incl. C++'s
  `UNKNOWN_ENUM_VALUE_<Enum>_<n>`), `to_ll`/`to_ull`/`to_d` (C `strto*`
  longest-prefix semantics), `parse_scalar` (int32/uint32 wrap like a
  `static_cast`), `has_presence`, `is_map`, `is_repeated`.
- `runtime/xml.py` → `harpia_runtime.xml` (task 2): `to_xml`, `from_xml`,
  `from_xml_element`, `escape`, `xsd`. A line-for-line port of
  `harpia_xml.h`, **byte-identical** (root = type name; presence-gated
  message/`optional` fields; proto3 scalars always emitted; maps as
  `<f><key>..</key><value>..</value></f>`). Reading uses
  `xml.etree.ElementTree` and merges, like the C++ reader. Python includes
  `xsd()`; the Java target skipped it.

- `runtime/yaml.py` → `harpia_runtime.yaml` (task 3): `to_yaml`, `from_yaml`,
  `quote`. A port of `harpia_yaml.h`, **byte-identical**; the reader parses
  exactly the emitted subset (indentation-driven recursive descent) and
  merges. Not PyYAML: the generated project has no `pyyaml` dependency.

- `runtime/serialize.py` → `harpia_runtime.serialize` (task 4): `Format`
  (`JSON`/`XML`/`YAML`), `format_name`, `to_string`, `from_string`,
  `tree_has_phi`, `redacted_to_string`. A phi-free type tree goes straight to
  the engines (byte-identical to them); a phi-bearing tree renders through
  the port of C++'s redacting walk, quirks included (prints proto3 defaults,
  YAML strings get JSON escaping, JSON map keys escaped twice).
  **Byte-identical to C++ `harpia::serialize::to_string`** for every fixture
  message, redaction on and off.
- `runtime/redaction.py` → `harpia_runtime.redaction`: `PLACEHOLDER`,
  `redaction_enabled`, `set_redaction_enabled`, `should_redact`.
- `runtime/redaction_audit.py` → `harpia_runtime.redaction_audit`:
  `allow_phi_print(sink=None, reason="")` records
  `phi_unredacted_output_enabled` then disables; `restore_phi_redaction`
  re-enables then records `phi_unredacted_output_disabled`. The only module
  here that imports the compliance runtime, so the adapter also copies
  `harpia_runtime.compliance.audit_sink`.
- **Generated** `harpia_generated/serialize/phi_registry.py`
  (`templates/phi_registry.py.tmpl`): `PHI_FIELDS` (the same schema-order
  pairs `SerializeAdapter` renders for C++), `is_phi`, `message_has_phi`.

## Key facts / gotchas
- Redacted text is a lossy view. JSON with a placeholder in a numeric field
  doesn't parse. Redacted XML/YAML parses, but only **numeric** phi fields
  come back at their default: a **string** phi field reads the literal
  `[REDACTED]` (C++ behaves the same; the task text said "default").
- **YAML known differences from the C++ reader** (found 2026-10-04; the C++
  runtime was not changed — flagged to Rafael):
  - (fixed, cpp-yaml-empty-mapping-DEFECT) `from_yaml("{}")` — to_yaml's
    empty document at column 0 — returns `True` in both runtimes now.
  - A map with a negative integer key (`-5: ...`) round-trips in neither
    runtime: the key line starts with `-` and reads as a sequence item. The
    parity fixture therefore uses non-negative map keys.
  - Otherwise `from_yaml`'s bool matches C++, including `False` for a
    document whose only content is empty lists (`f: []`, nothing matched).
- **JSON is byte-identical to C++** for every fixture message (156 types,
  stress strings included; checked 2026-10-04). Plain `json.dumps` differed
  in one way: C++ escapes `<`/`>` as `\u003c`/`\u003e` inside strings.
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
