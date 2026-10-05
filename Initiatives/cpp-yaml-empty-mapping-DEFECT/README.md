# C++ `from_yaml("{}")` returns false — DEFECT

**Status: scoped, not started.** Found 2026-10-04 while porting the YAML
runtime to Python (python-target `py-serialization/3`; decisions log item 11
in `Initiatives/python-target/NEXT_SESSION.md`). The C++ code was not changed.

## What was found

`YamlAdapter/runtime/harpia_yaml.h`, `from_yaml` (~line 464):

```cpp
// ... an empty document or "{}" is a valid empty message and returns true.
inline bool from_yaml(const std::string& yaml, Message* msg) {
    const auto lines = detail::tokenize(yaml);
    ...
    detail::read_mapping(lines, i, 0, msg, hits);
    if (!lines.empty() && hits == 0) return false;
```

`to_yaml` of an all-default message emits `"{}\n"` (line ~457). `tokenize`
only drops blank lines and `---` / `...`, so `"{}"` survives as one line,
matches no field (`hits == 0`), and `from_yaml` returns **false** — the
opposite of its own header comment and of the python-target task spec.
Consequence: `from_yaml(to_yaml(empty_msg))` reports "not our format"; an
all-default message does not round-trip through the C++ YAML API.

The Python runtime (`PySerialization/runtime/yaml.py`) already returns
**true** (it followed the spec), so C++ and Python currently disagree on this
one input.

## Scope

One epic, one task: make C++ match its documented contract. No output-byte
change (`to_yaml` is untouched) → `UnitTests/golden/` does not move.

See `epics/README.md`.
