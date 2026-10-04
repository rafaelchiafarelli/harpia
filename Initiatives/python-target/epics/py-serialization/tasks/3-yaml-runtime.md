## YAML runtime — byte-identical port of `harpia_yaml.h` (no PyYAML at runtime)

- **Depends on:** task 2 (shares its number-formatting/presence helpers).
- **Contract:** `harpia_runtime/yaml.py`. A port of
  `YamlAdapter/runtime/harpia_yaml.h`, providing `to_yaml(msg) -> str` and
  `from_yaml(text, msg) -> bool`.
  - Emitted shape exactly as `YamlAdapter/CLAUDE.md` describes: block
    style, two-space indent, top-level mapping with no wrapper key, strings
    always double-quoted with `\ " \n \t` escapes, `{}`/`[]` for empty,
    `- ` sequences of mappings, maps as nested mappings.
  - `from_yaml` parses **exactly the subset** `to_yaml` emits
    (indentation-driven recursive descent) and returns `False` only when
    nothing matched.
  - **Not** PyYAML. A general YAML parser would accept and emit forms the
    C++ runtime doesn't, breaking byte parity and the subset contract.
    The generated project gains no `pyyaml` dependency.
- **Bar:** byte-identical to C++ `to_yaml` for every fixture message.
  `from_yaml(C++ output)` equals the original.
- **Out of scope:** redaction (task 4).
- **Tests:**
  - Unit tests (flat / nested-repeated / map / empty-document `{}` → valid
    empty message).
  - A protoc+g++-gated byte-parity test against a C++ probe (the
    `test_stage10_yaml.py` build shape).
