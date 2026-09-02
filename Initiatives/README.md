# Initiatives index

Scoping/planning docs for work bigger than a single session. Each entry is
either a **live plan** (being executed slice by slice) or a **scoping doc**
(recommendation + sizing, not yet started). `README.md`'s "Known gaps" section
is the authoritative implemented-vs-missing list; this index is the *why/how*
behind the larger unimplemented pieces.

## How to work an `epics/` folder

The full process — the Initiative → Epic → Task → Contract hierarchy, the
matching branch hierarchy, the per-task implementation loop, and the
stop-and-flag rules — lives in the **`harpia-workflow` skill**
(`.claude/skills/harpia-workflow/SKILL.md`). Read it first. Repo-specific
points it doesn't cover:

- **Layout.** `Initiatives/<initiative>/epics/<epic>/tasks/<n>-<task>.md`. Task
  files carry a numeric prefix restarting at `1` per epic — that number is the
  implementation order and the branch name. The done marker is a `-done`
  **filename** suffix (`git mv` at land time), never a status line inside the
  file. Cross-epic execution order lives in each initiative's `epics/README.md`.
- **Per task, in order:** implement → regenerate goldens
  (`HARPIA_UPDATE_GOLDEN=1 pytest UnitTests/test_golden.py
  UnitTests/test_golden_java.py`) and **review the diff** → full suite green in
  Docker (`Docker/run.sh pytest UnitTests/`) → commit the implementation →
  `git mv` the task file to its `-done` name in a second commit → merge
  `--no-ff` up the branch chain → branch the next task. Land additive where
  possible unless the task says otherwise.
- **A new fixture goes in `HarpiaTest/Include/*.harpia`, not `test.harpia`** —
  only the root file's text feeds the pinned `HASH` constants in
  `UnitTests/*.py`, so an Include edit moves golden *content* for the touched
  messages but leaves every `HASH = "…"` alone. `.harpia` comments are lexed
  like code: letters/digits/spaces and `. , ( ) { } [ ] ; = < > + - * /` only —
  a `:` / `'` / `"` / `_` / backtick anywhere in a `//` comment hard-errors the
  file.

## Index

| Doc | Status |
|---|---|
| [feature-examples/](feature-examples/README.md) | **Partly shipped.** Fixture cleanup shipped 2026-08-24. The `worked-examples` epic (one small runnable example per generated feature + an index) — not started. |
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | **Shipped** (Foundation F6 + Ground Rule 6, 2026-08-23). Lives on as a living pitfall-table reference every epic appends to. |

Finished plans are removed from this index once done — the shipped behavior is
documented in the code's own `CLAUDE.md` files. The **medical_devices**
initiative (the medical-device compliance profile: `phi` encryption + audit,
`critical` delivery, mTLS/RBAC/sessions, DDS, events, serialization, SBOM, …)
shipped in full as **V1** (2026-09-02) and its plan folder was removed; the
shipped behavior is in `harpia.process.md`, `USAGE.md`, and the module
`CLAUDE.md` files. Earlier removed-on-completion plans: Postgres backend
(`Database/CLAUDE.md`), crash/interrupt recovery (`Util/CLAUDE.md`),
message-versioning (`Message/CLAUDE.md`, `Capability/CLAUDE.md`),
multi-language Java target (`GradleAdapter/CLAUDE.md` et al.).

## Backlog

- **Python as language #3** (after Java, shipped 2026-08-25). Was the original
  per-stage-cost recommendation; deferred when an existing Android fleet
  created a concrete need for generated Java. A cross-language `DbBackend`-style
  seam was left undesigned after Java (`Database/CLAUDE.md`) — Python would be
  the third data point, likely the trigger to design one. Multi-session sized.
