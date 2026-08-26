# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps. `initiatives/README.md` is the backlog/scoping-doc index —
open items that used to accumulate in this file now live there instead;
this file stays a short handoff note, not an archive.

Two real generator bugs were found on 2026-08-26 while scaffolding the HMS /
Hospital-Point-of-Information / Ward-Information-Integrator example projects
(branch `feature/test-projects-blueprint`, commit `e807666`). That branch has
**workarounds** in place and does not touch the generator — the fixes belong
here, on `dev`.

## Open bug 1: lexer matches bare-word type keywords as identifier prefixes

**Symptom.** A `.harpia` with `enum integrator_link_state { unknown = 0; ... }`
fails codegen with:

```
[MessageCreator] ... ErrorType:NO_NAME_IN_MESSAGE ErrorClass:MESSAGES
    at File:.../ward_information_integrator.harpia, line:5 and Character:5
```

**Root cause.** `LexicalAnalizer/LexicalAnalyzer.py`: `self.rules` is an ordered
list joined into a single alternation regex (`tokens_join = '|'.join(...)`,
~line 85) and Python `re` alternation is **leftmost-alternative-wins, not
longest-match**. The rule `('INT32', r'int')` has no word boundary and no
trailing space, so at the start of `integrator_link_state` it matches `int`,
and the identifier lexes as `INT32("int")` + `ID("egrator_link_state")`. The
enum name is then not an `ID`, so `message/Message.py::Message.Process()`
(the `lastToken == "ENUM"` branch, ~line 58-66) raises `NO_NAME_IN_MESSAGE`.

This is the same bug class as the existing INT64-before-INT32 comment in that
file (~line 30-47): `int64` was silently lexed as `int` + `64`. The unanchored
bare-word rules are `INT32 (int)`, `INT64 (int64)`, `FLOAT (float)`,
`STRING (string)`, `MAP (map)`, `IMPORT (import)`, `REPETEABLE (repeteable)`,
`PAGINATION (pagination)`. The modifier keywords (`enum `, `stream `, `pull `,
`push `, `event `, `phi `, `optional `, `required `, `unique `, `message `) are
protected by a **required trailing space**, so `event_id` etc. are fine; the
eight bare-word rules above are not.

**Repro.** Any message / enum / field identifier starting with one of those
keywords, e.g.:

```
push message internal_state { required int x; } internal_state_table;
```

**Suggested fix.** Anchor the bare-word keyword rules with a trailing word
boundary: `('INT32', r'int\b')`, `('FLOAT', r'float\b')`, `('STRING',
r'string\b')`, `('INT64', r'int64\b')`, `('MAP', r'map\b')`, `('IMPORT',
r'import\b')`, `('REPETEABLE', r'repeteable\b')`, `('PAGINATION',
r'pagination\b')`. With `int\b` the INT64-before-INT32 ordering is no longer
load-bearing (leave it anyway). Run the full `pytest` suite + the `HarpiaTest`
fixtures to confirm no fixture relied on the loose match.

**Workaround on the feature branch.** Renamed `integrator_link_state` ->
`uplink_state` (and `integrator_link_status` -> `uplink_status`). Constraint is
also recorded in `TestProjects/CLAUDE.md`.

## Open bug 2: first-ever generation fails under `run_harpia.sh` (read-only input mount)

**Symptom.** For a brand-new project folder (no `schema_registry/` yet):

```
bash ./run_harpia.sh TestProjects/<new-project> TestProjects/_gen/<x> --no-build
...
Traceback (most recent call last):
    messagesErrors = msgFactory.CreateMessages(beginToken=0)
OSError: [Errno 30] Read-only file system: '/harpia_input/schema_registry'
```

**Root cause.** `run_harpia.sh` mounts the input folder read-only
(`-v "$INPUT_ABS":"$C_INPUT":ro`, ~line 105). On the **first** generation the
pipeline calls `freezeFieldNumbers(...)` (from `message/Message.py`) which
writes `schema_registry/<stem>/<msg>.fieldmap` **next to the `.harpia`, inside
the input folder**, to freeze wire numbers. The `:ro` mount makes that write
throw and codegen aborts. On every later run the sidecar already exists and is
only read, so `:ro` is fine — this is a first-run-only failure, which is why
the 15 pre-existing TestProjects were unaffected.

**Repro.** Delete a project's `schema_registry/` and re-run `run_harpia.sh`
against it.

**Workaround used this session.** Run the first-gen pass with a direct
`docker run` that mounts the whole repo read-write and sets the env vars
directly:

```sh
docker run --rm -i -u "$(id -u):$(id -g)" -v "$PWD":/harpia -w /harpia \
  -e HARPIA_INPUT_FILE=/harpia/TestProjects/<room>/<proj>/<name>.harpia \
  -e HARPIA_INCLUDE_FOLDER=/harpia/TestProjects/<room>/<proj>/Include \
  -e HARPIA_OUTPUT_DIR=/harpia/TestProjects/_gen/<proj> \
  harpia-build bash -c 'python3 main.py'
```

Then commit the produced `schema_registry/`; after that `run_harpia.sh` works
normally. The 5 new projects' committed `schema_registry/` sidecars were made
this way, not via `run_harpia.sh`. Also documented in `TestProjects/README.md`
("First generation") and `TestProjects/CLAUDE.md`.

**Suggested fix (pick one).**
1. Minimal: in `run_harpia.sh`, when the input folder has no `schema_registry/`,
   do the first pass with a read-write bind (or against a temp copy of the
   input folder) and copy the resulting `schema_registry/` back to the host
   input folder; keep `:ro` for the steady-state path.
2. Cleaner: give the pipeline an explicit output location for the registry
   (e.g. `HARPIA_SCHEMA_REGISTRY_DIR`, or write it under the output folder)
   instead of always writing next to the `.harpia`; `run_harpia.sh` then points
   it somewhere writable. Keeps the input folder a strictly read-only source.
3. Blunt: mount the input read-write in `run_harpia.sh` — simplest, but drops
   the "input folder is never modified by codegen" guarantee.
