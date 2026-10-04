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
| [multi-system-reference/](multi-system-reference/README.md) | **Epics 1–4 shipped in V2 (2026-10-04)**: Java/Android hardened client, pooled DB servers, the three-program hardened reference system (`HarpiaTest/app_example/multi_system/`) and the load harness. **Open:** epic 5 `windows-verification` (real Windows `station`), delegated to the Windows session. |
| [feature-examples/](feature-examples/README.md) | **Partly shipped.** Fixture cleanup shipped 2026-08-24. The `worked-examples` epic (one small runnable example per generated feature + an index) — not started. |
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | Foundation F6 + Ground Rule 6 plumbing **shipped** 2026-08-23. The `doc-comment-coverage` epic (real per-template doc-comments) — **not started**, after `multi-system-reference`. |
| [ci-pipeline/](ci-pipeline/README.md) | **Scoped, not started.** GitHub Actions running the existing `Docker/run.sh pytest UnitTests/` suite on push/PR, plus image-layer caching. 2 tasks, both written. Highest leverage-per-effort of the open initiatives — no CI today means nothing independently re-verifies any "N passed" claim. |
| [python-target/](python-target/README.md) | **Planned, not started — all 14 epics / 54 tasks written (2026-10-03).** Language #3 (resequenced ahead of Go at another project's request): full C++ compliance parity with no carve-outs (DDS + CURVE/ZAP included), stdlib + standard C-extension bindings, generation-time codegen under `<dest>/python/`. Epic 0 is the `LangBackend` seam (moved here from go-target). No FHIR façade (C++ has none). Ends with a C++/Java/Python interop epic. Implement after `multi-system-reference`'s chain clears this clone, or in a separate clone. |
| [go-target/](go-target/README.md) | **Scoped, not started.** Language #4 (resequenced behind python-target 2026-10-03), full compliance parity except DDS + ZMQ-CURVE/ZAP (pure-Go constraint). Depends on python-target's `lang-backend-seam` epic; its interop epic adds Go as the 4th peer to python-target's harness. No task files yet. |

Finished plans are removed from this index once done — the shipped behavior is
documented in the code's own `CLAUDE.md` files. The **medical_devices**
initiative (the medical-device compliance profile: `phi` encryption + audit,
`critical` delivery, mTLS/RBAC/sessions, DDS, events, serialization, SBOM, …)
shipped in full as **V1** (2026-09-02) and its plan folder was removed; the
shipped behavior is in `harpia.process.md`, `USAGE.md`, and the module
`CLAUDE.md` files. The **message-level-hardening** initiative (`protected`/`open` per-message
hardening modifiers) shipped 2026-09-19 — see `USAGE.md` §8.1,
`harpia.process.md`, `Database/CLAUDE.md`. The **transport-multipeer-coverage**
initiative (N-peer ZMQ PUB/SUB fan-out + PUSH/PULL load-balance, C++ and
C++↔Java) shipped 2026-09-26 — see `HarpiaTest/app_example/fanout/README.md`
and `UnitTests/test_zmq_*fanout*.py` / `test_zmq_*pushpull*.py`.
Earlier removed-on-completion plans: Postgres backend
(`Database/CLAUDE.md`), crash/interrupt recovery (`Util/CLAUDE.md`),
message-versioning (`Message/CLAUDE.md`, `Capability/CLAUDE.md`),
multi-language Java target (`GradleAdapter/CLAUDE.md` et al.).

## Backlog

- ~~**Python as language #3**~~ — now [python-target/](python-target/README.md),
  language #3 again since 2026-10-03 (it was briefly #4 behind Go). The
  cross-language `LangBackend` seam lives in its epic 0.
