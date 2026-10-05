## C++ YAML reader: `-` starts a sequence item only when followed by space / EOL

- **Depends on:** nothing.
- **Deliverable:** in `YamlAdapter/runtime/harpia_yaml.h`, one helper (e.g.
  `detail::is_seq_item(const std::string&)`: `s[0]=='-' && (s.size()==1 ||
  s[1]==' ')`) used at every place that currently tests `s[0] == '-'` /
  `s[0] != '-'` (read_sequence, read_mapping, the map/child-block readers).
  `to_yaml` output unchanged.
- **Out of scope:** Python runtime (task 2); quoting keys on the write side.
- **Tests:**
  - C++ round-trip of a `map<int32,…>` / `map<int64,…>` / `map<sint*,…>` with
    keys `{-5, 0, 7, INT_MIN}` (top-level and nested in a repeated message).
  - Existing YAML tests (sequences of scalars and of messages, `- {}` items)
    unchanged.
- **Docs:** `YamlAdapter/CLAUDE.md` — the item-vs-key rule.
