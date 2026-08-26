# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps. `initiatives/README.md` is the backlog/scoping-doc index —
open items that used to accumulate in this file now live there instead;
this file stays a short handoff note, not an archive.

## Resolved 2026-08-26: two generator bugs found while scaffolding TestProjects

Both were reported here after being found (with workarounds only) on branch
`feature/test-projects-blueprint` (commit `e807666`). Both are now fixed on
`dev`; full `pytest` suite green (200 passed, 4 pre-existing skips).

**Bug 1 — lexer matched bare-word type keywords as identifier prefixes.**
`LexicalAnalizer/LexicalAnalyzer.py`'s rule table is joined into one
alternation regex and Python `re` alternation is leftmost-alternative-wins,
not longest-match. The unanchored rules `int`, `int64`, `float`, `string`,
`map`, `import`, `repeteable`, `pagination` matched the *start* of an
identifier — `integrator_link_state` lexed as `int` + `egrator_link_state`
and failed with `NO_NAME_IN_MESSAGE`. Fix: anchored all eight with a trailing
`\b`. The modifier keywords (`enum `, `stream `, … `message `) were already
protected by a required trailing space. The feature branch's workaround
(renaming `integrator_link_state` → `uplink_state` etc.) can be reverted.

**Bug 2 — first-ever generation failed under `run_harpia.sh` (`:ro` input mount).**
On the first generation of a message, `message/FieldMap.py::freeze()` writes
`schema_registry/<stem>/<msg>.fieldmap` next to the `.harpia`, inside the
input folder; `run_harpia.sh` mounted that folder `:ro`, so the write threw
`OSError: [Errno 30] Read-only file system`. Later runs only read the sidecar,
so `:ro` was fine then — a first-run-only failure. Fix: `run_harpia.sh` now
mounts the input folder read-write **only** when it contains no
`schema_registry/` anywhere (brand-new project), prints a `mount :` line
saying so and to commit the sidecars, and reverts to `:ro` once the registry
exists. The "codegen never mutates its input" guarantee still holds for every
run after the first.
