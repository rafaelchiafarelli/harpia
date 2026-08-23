# HarpiaTest — sample `.harpia` input + generated output tree

**Role:** The canonical demo/test input the pipeline runs on by default, plus its generated build output. `main.py` defaults: input `./HarpiaTest/test.harpia`, includes `./HarpiaTest/Include`, output `./HarpiaTest/test_build` (all overridable via `HARPIA_INPUT_FILE`, `HARPIA_INCLUDE_FOLDER`, `HARPIA_OUTPUT_DIR`).

## Contents
- `test.harpia` — root input. Starts with `import "file1.harpia"` / `file2` / `file3` (resolved from `Include/`). Exercises messages, nested messages, enums, `optional`/`required`/`repeteable`, `map<>`, `pagination[N]`, and stream/pull/push/event message modifiers plus comment styles.
- `Include/file1.harpia` (`message pope`), `file2.harpia` (`message king`), `file3.harpia` (`message queen`, plus fixtures added for specific generator features: `courier` — PUSH-only, exercises the ZMQ many-to-* runtime origin id; `parcel`/`shipment` — a repeated field targeting a table-less composed message (`RepeatedComposedField`); `waypoint`/`route`/`journey` — a composed field nested two levels deep inside an embedded table-less message) — module files pulled in by the root's `import` statements. **Only the root file's own md5 is used to tag every message** (see LexicalAnalizer/CLAUDE.md), so editing an Include file's content never perturbs the pinned `HASH` constants in `tests/` — this is why new fixtures land in Include files, not `test.harpia` itself.
- `test_build/` — GENERATED output (proto, generated/cpp adapters, CMake, server/client demo). Regenerated write-if-different each run, not wiped (`Util.util.write_if_different`/`prune_stale_outputs`, called from `main.py`) — an unchanged file keeps its mtime; a message renamed/removed since the last run has its old output pruned.
- `schema_registry/` — COMMITTED sidecar (per-message `.fieldmap` files: `test/<MessageName>.fieldmap`), NOT generated output despite living next to `test_build/`. Written by `message/FieldMap.py` (see `message/CLAUDE.md`) to freeze each field's protobuf wire number across regenerations. Deliberately outside `test_build/` so a wholesale rebuild of that dir can't blow it away.

## Key facts / gotchas
- `test_build/` is **generated and gitignored** (repo `.gitignore` has `*build*`). Never edit by hand or commit; regenerate by running the pipeline.
- `schema_registry/` is the opposite: **committed, never gitignored, never hand-edited.** It's the only thing under `HarpiaTest/` that a generation run writes to but that must survive across runs and across `git clean`; treat a diff here the way you'd treat a `.proto` field-number diff -- read it before committing.
- Input md5 (current golden input, for detecting drift):
  - `test.harpia` = `c96f8fd7f45108efee5a8ecb43eab1da`
  - `Include/file1.harpia` = `e7f528d62098cd94d92019bda39c8f43`
  - `Include/file2.harpia` = `f9ea5ac8ffa3e7d57e6a95824840d191`
  - `Include/file3.harpia` = `c3d7c48789d7f8b364afed7e6bad0114`
- Imports are resolved by filename against `includeFolder`; the root file references them bare (`file1.harpia`), not by relative path.
