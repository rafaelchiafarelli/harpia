# `test_yaml_map_negative_int_keys` fails intermittently — DEFECT

**Status: scoped, not started; cause not confirmed.** Found 2026-11-01.

## What was found

`UnitTests/test_stage10_yaml.py::test_yaml_map_negative_int_keys` fails on some
runs and passes on others, with no code change between them. It is the only
intermittent failure seen in the suite.

- **Where:** always the nested half, on `data` (a `prince` with a `map<int,
  string>` plus a repeated field): `negative map keys (nested) failed at #2`,
  the `a.SerializeAsString() != b.SerializeAsString()` check at
  `test_stage10_yaml.py:294`. `from_yaml` itself returned true (that is #1).
- **How often:** 3 of 8 runs on `dev` at `a1ecf3b`, which has none of the
  2026-11-01 handoff code; 1 of 5 on a later branch; 2 of 4 full-suite runs.
- **Sample YAML at a failure:** the map came out as `2: "pos"` then `-1: "neg"`,
  though the test inserts `-1` first.

## Unconfirmed hypothesis

Protobuf doesn't guarantee a stable byte order for map fields, so the test may
be comparing bytes of two equal messages whose maps hold their entries in a
different order. That would make this a **test bug**. The other outcome is a
**product bug**: `from_yaml` really loses or changes a value on some runs. The
task below decides which; don't assume the first.

## Scope

One epic, **`map-roundtrip`**, one task — see
`epics/map-roundtrip/tasks/1-find-and-fix-the-flake.md`.
