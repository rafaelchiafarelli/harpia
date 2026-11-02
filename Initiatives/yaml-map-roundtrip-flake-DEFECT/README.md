# `test_yaml_map_negative_int_keys` fails intermittently — DEFECT

**Status: fixed; a test bug.** Found and fixed 2026-11-01.

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

## Cause

The test compared bytes of two equal messages whose maps hold their entries in a
different order. In protobuf 3.21.12 every map takes its own hash seed from its
address and the CPU timestamp counter (`Seed()` in `map.h`), and
`SerializeAsString()` writes map entries in iteration order. So `from_yaml` was
right and the comparison was wrong.

A copy of the nested half, run 500 times: `from_yaml` returned true and
`MessageDifferencer::Equals` held on all 500. The bytes differed on 276, exactly
the runs where the two maps iterated in different orders. With two entries the
expected failure rate is about 1 in 2, not the 1 in 3 first estimated; the task's
loop failed 13 of 20 before the fix.

`to_yaml` writes map entries in the same order, so equal messages can produce
different YAML text. Nothing here depends on that, so it was left as it is.

## Scope

One epic, **`map-roundtrip`**, one task — see
`epics/map-roundtrip/tasks/1-find-and-fix-the-flake-done.md`.
