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

## Working the `*-DEFECT` initiatives

Every DEFECT task follows the same three steps, written into each task file:

1. **Corroborate (red first).** Write the named unit test before touching the
   code under fix and run it on the unmodified tree. It must fail (or, where a
   strict xfail already pins the defect, xfail for the stated reason). If it
   passes, the defect isn't real: record that in the commit, mark the task
   `-done` with no code change, and stop.
2. **Fix.** Only the task's deliverable.
3. **Unit test stays.** The red test is now green and is kept as the
   regression test; strict xfails pinning the defect are un-marked.

Open DEFECT initiatives: see the `*-DEFECT` rows of the index below.

## Index

| Doc | Status |
|---|---|
| [multi-system-reference/](multi-system-reference/README.md) | **Epics 1–4 shipped in V2 (2026-10-04)**: Java/Android hardened client, pooled DB servers, the three-program hardened reference system (`HarpiaTest/app_example/multi_system/`) and the load harness. **Open:** epic 5 `windows-verification` (real Windows `station`), delegated to the Windows session. |
| [feature-examples/](feature-examples/README.md) | **Partly shipped.** Fixture cleanup shipped 2026-08-24. The `worked-examples` epic (one small runnable example per generated feature + an index) — not started. |
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | Foundation F6 + Ground Rule 6 plumbing **shipped** 2026-08-23. The `doc-comment-coverage` epic (real per-template doc-comments) — **not started**, after `multi-system-reference`. |
| [ci-pipeline/](ci-pipeline/README.md) | **Scoped, not started.** GitHub Actions running the existing `Docker/run.sh pytest UnitTests/` suite on push/PR, plus image-layer caching. 2 tasks, both written. Highest leverage-per-effort of the open initiatives — no CI today means nothing independently re-verifies any "N passed" claim. |
| [cpp-phi-unencrypted-field-shapes-DEFECT/](cpp-phi-unencrypted-field-shapes-DEFECT/README.md) | **Defect, not started** (found 2026-10-05 while fixing the numeric-phi defect). `phi` on an enum field, an embedded sub-field, a repeated or a map field is stored in plaintext by the C++ and Python DAOs, with no audit. 3 tasks; task 1 is a refuse-vs-encrypt decision. |
| [transitive-imports-DEFECT/](transitive-imports-DEFECT/README.md) | **Defect, not started** (reported 2026-10-31). Only modules the root imports directly are generated; a module imported by an included file is silently skipped. 1 task. |
| [dao-key-access/](dao-key-access/README.md) | **Scoped, not started** (requested 2026-10-31 by `mocap-contracts`). Generated `read_by_<unique field>` DAOs, and an explicit `.harpia` opt-in for a database-assigned primary key (decided 2026-11-01: `autokey` modifier, preset key is an error, key written back). 2 epics, 7 tasks (1 done). |
| [embed-presence-DEFECT/](embed-presence-DEFECT/README.md) | **Defect, not started** (found 2026-11-01 closing the mocap handoff). An unset embedded (table-less) message field reads back present: no column records the embed's own presence. Decided: hidden `HARPIA_HAS_<path>` column per embed (option B). 3 tasks. |
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
The nine **python-target findings** (`*-DEFECT` initiatives, fixed
2026-10-05, shipped in **V3**): PG migration introspection limited to
`current_schema()`, `LocalKeyProvider` store `0600` + loose-store refusal
(C++ + Python), phi scalar columns TEXT in the DDL, DAO `list` ordered by the
primary key (C++ + Java), `JdbcBind` NULL reads + Java DAO child-table
disclosure, ZMQ `runtime_origin_id()` guard, C++ `from_yaml("{}")`, negative
YAML map keys (C++ + Python), Java XML byte parity — see `Database/CLAUDE.md`,
`Crypto/CLAUDE.md`, `JavaDatabase/CLAUDE.md`, `ZmqAdapter/CLAUDE.md`,
`YamlAdapter/CLAUDE.md`, `PySerialization/CLAUDE.md`,
`JavaXmlAdapter/CLAUDE.md`. Each has its regression test.
The **stable-hidden-names-DEFECT** (reported by `mocap-contracts`, fixed
2026-11-01): hidden fields are the fixed `HARPIA_ID` / `HARPIA_STATUS` /
`HARPIA_ERROR` / `HARPIA_ORIGINATOR` (no root-file hash), and the C++ and
Python migrations rename legacy `ID_<md5>`-style columns in place — see
`Message/CLAUDE.md`, `Database/CLAUDE.md`, `PyDatabase/CLAUDE.md`, `USAGE.md`
§10/§16.
The **db-optional-presence-DEFECT** (fixed 2026-11-01, also reported by
`mocap-contracts`): an unset `optional` field — top level or an embedded flat
column — is stored as NULL and reads back unset in the C++, Python and Java
DAOs; an unset `phi optional` stores NULL unencrypted; pre-fix rows keep
reading present — see `Database/CLAUDE.md`, `PyDatabase/CLAUDE.md`,
`JavaDatabase/CLAUDE.md`, `USAGE.md` §16. The **python-target** initiative
(language #3, shipped in V3) — its folder and the `NEXT_SESSION.md` decision
log (items 1-48) were removed 2026-11-01; the log is in git history.
Earlier removed-on-completion plans: Postgres backend
(`Database/CLAUDE.md`), crash/interrupt recovery (`Util/CLAUDE.md`),
message-versioning (`Message/CLAUDE.md`, `Capability/CLAUDE.md`),
multi-language Java target (`GradleAdapter/CLAUDE.md` et al.).

## Backlog

- ~~**Python as language #3**~~ — shipped as python-target (V3); its plan
  folder was removed 2026-11-01 (git history, e.g. `git show
  bb7a6be:Initiatives/python-target/README.md`).
