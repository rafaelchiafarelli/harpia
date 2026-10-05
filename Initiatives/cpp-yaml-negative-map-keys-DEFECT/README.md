# Negative integer map keys don't round-trip through YAML — DEFECT

**Status: scoped, not started.** Found 2026-10-04 while porting the YAML
runtime to Python (python-target `py-serialization/3`; decisions log item 12
in `Initiatives/python-target/NEXT_SESSION.md`). The C++ code was not changed;
the Python port reproduces the same behavior (ported as-is for parity), and
the parity fixture currently dodges it by using non-negative map keys only.

## What was found

`to_yaml` writes a `map<int*, …>` entry with a negative key as a bare mapping
line, e.g. `-5: "x"`. The reader decides "sequence item vs. mapping key" on the
first character alone — `YamlAdapter/runtime/harpia_yaml.h`:

- `read_sequence` (~line 341): `L[i].s[0] == '-'` → sequence item
- `read_mapping` / map reader (~lines 386, 430, 443): `L[i].s[0] != '-'` →
  mapping key

So `-5: "x"` is read as a sequence item, the map entry is lost (or misparsed),
and `from_yaml(to_yaml(msg)) != msg` for any message holding a negative int
map key. Same bug in `PySerialization/runtime/yaml.py` (deliberate parity).

## Scope

One epic: **`yaml-negative-keys`** — fix the C++ reader (task 1), then mirror
it in the Python runtime (task 2, only once python-target has merged to the
branch the fix lands on). See `epics/README.md`.
