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
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | Foundation F6 + Ground Rule 6 plumbing **shipped** 2026-08-23. The `doc-comment-coverage` epic (real per-template doc-comments) — **not started**, next up. |
| [transport-multipeer-coverage/](transport-multipeer-coverage/README.md) | **Scoped, not started.** N-subscriber PUB/SUB fan-out + N-puller PUSH/PULL load-balance + cross-language (C++/Java) versions, currently proven only 1:1. Sequenced right after doxygen. |
| [go-target/](go-target/README.md) | **Scoped, not started.** Language #3, full compliance parity except DDS + ZMQ-CURVE/ZAP (pure-Go constraint). `lang-backend-seam` epic's tasks are written; sequenced after `transport-multipeer-coverage`. |
| [python-target/](python-target/README.md) | **Scoped, not started.** Language #4, full compliance parity with no carve-outs (stdlib + standard C-extension bindings, not pure-Python). Sequenced after the entire `go-target` initiative ships. Supersedes the old "Python as language #3" backlog item below. |

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

- ~~**Python as language #3**~~ — superseded 2026-09-03 by
  [python-target/](python-target/README.md) (now language #4, planned in
  full). The cross-language `LangBackend`-style seam this item used to say
  Python "would likely be the trigger to design" is instead being designed
  now, ahead of Go, in `go-target/`'s `lang-backend-seam` epic.
