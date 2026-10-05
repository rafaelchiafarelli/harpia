## C++ YAML reader: `-` starts a sequence item only when followed by space / EOL

- **Depends on:** nothing.
- **1. Corroborate (red first):** add
  `UnitTests/test_stage10_yaml.py::test_yaml_map_negative_int_keys` — a C++
  round trip of a message with `map<int32,…>` / `map<int64,…>` /
  `map<sint*,…>` holding keys `{-5, 0, 7, INT_MIN}`, top-level and nested in a
  repeated message (add the fixture message to `HarpiaTest/Include/*.harpia`
  if none has these key types — that fixture is pre-work). Assert
  `from_yaml(to_yaml(m)) == m`. On unmodified code it must **fail** (the
  negative-key lines start with `-` and are read as sequence items at
  `harpia_yaml.h` ~341/386/430/444, so entries are lost/misparsed). If it
  passes, stop and record the finding; no code change.
- **2. Fix:** in `YamlAdapter/runtime/harpia_yaml.h`, one helper
  `detail::is_seq_item(const std::string&)` (`s[0]=='-' && (s.size()==1 ||
  s[1]==' ')`) used at every place that tests `s[0] == '-'` / `s[0] != '-'`
  (read_sequence, read_mapping, read_map, apply_entry). `to_yaml` unchanged.
- **3. Unit tests (required, kept):**
  - `test_yaml_map_negative_int_keys` (above) — now green.
  - Existing `test_yaml_nested_and_repeated` / `test_yaml_map_roundtrip`
    (sequences of scalars and of messages, `- {}` items) unchanged and green.
- **Out of scope:** Python runtime (task 2); quoting keys on the write side
  (that would move `to_yaml` bytes — a contract change, ask first).
- **Golden:** none expected; if any golden moves, stop and ask.
- **Docs:** `YamlAdapter/CLAUDE.md` — the item-vs-key rule.
