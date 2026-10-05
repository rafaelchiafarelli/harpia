## C++ `from_yaml` accepts a `{}` document as a valid empty message

- **Depends on:** nothing (shipped `YamlAdapter/runtime/harpia_yaml.h`).
- **1. Corroborate (red first):** add
  `UnitTests/test_stage10_yaml.py::test_yaml_empty_mapping_document` — a C++
  driver over a generated message asserting `from_yaml(to_yaml(default_msg))`,
  `from_yaml("{}")`, `from_yaml("{}\n")` and `from_yaml("---\n{}\n")` each
  return `true` and leave the message equal to default. On unmodified code it
  must **fail** (`from_yaml` returns `false`: `{}` survives `tokenize`, matches
  no field, `hits == 0`). If it passes, the defect isn't real: stop, record
  the finding in the commit, mark the task done with no code change.
- **2. Fix:** in `YamlAdapter/runtime/harpia_yaml.h`, a document whose only
  content line is `{}` (after `tokenize` drops blanks / `---` / `...`) makes
  `from_yaml` return `true` and leaves `msg` default. Every other `hits == 0`
  case still returns `false`.
- **3. Unit tests (required, kept):**
  - `test_yaml_empty_mapping_document` (above) — now green.
  - `test_yaml_unknown_keys_only_is_rejected` — a document of only unknown
    keys still returns `false` (regression guard for the "not our format"
    signal).
  - Parity: add `{}` to the YAML cases in `UnitTests/_py_cpp_parity.py` so
    `test_serialize_xlang3.py::test_yaml_cpp_equals_python` asserts C++ and
    Python agree on it.
- **Out of scope:** any change to `to_yaml` output; any other YAML subset
  change (negative map keys are `cpp-yaml-negative-map-keys-DEFECT`).
- **Golden:** none (parser-only). `test_golden*.py` must stay unchanged.
- **Docs:** `YamlAdapter/CLAUDE.md` — note the behavior now matches the header
  comment.
