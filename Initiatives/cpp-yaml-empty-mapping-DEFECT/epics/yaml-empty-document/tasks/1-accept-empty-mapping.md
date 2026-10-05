## C++ `from_yaml` accepts a `{}` document as a valid empty message

- **Depends on:** nothing (shipped `YamlAdapter/runtime/harpia_yaml.h`).
- **Deliverable:** in `YamlAdapter/runtime/harpia_yaml.h`, a document whose
  only content line is `{}` (after `tokenize` drops blanks / `---` / `...`)
  makes `from_yaml` return `true` and leaves `msg` cleared/default. Every other
  `hits == 0` case still returns `false`.
- **Out of scope:** any change to `to_yaml` output; any other YAML subset
  change (negative map keys are `cpp-yaml-negative-map-keys-DEFECT`).
- **Tests:**
  - C++ round-trip: `from_yaml(to_yaml(default_msg))` → `true`, message equals
    default. Also `"{}"`, `"{}\n"`, `"---\n{}\n"` → `true`.
  - Regression: a document of only unknown keys still returns `false`.
  - If the python-target parity harness (`UnitTests/_py_cpp_parity.py`) is on
    the branch, add `{}` to the YAML parity fixtures (C++ and Python must now
    agree).
- **Docs:** `YamlAdapter/CLAUDE.md` — note the behavior is now as documented.
