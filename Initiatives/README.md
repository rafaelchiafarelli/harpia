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

Run order (one chain per clone, so one at a time; worst impact first,
golden-moving tasks never in parallel):

1. `cpp-pg-introspection-schema-DEFECT` — data loss on shared PG databases.
2. `cpp-key-store-permissions-DEFECT` — KEK world-readable.
3. `cpp-phi-numeric-column-type-DEFECT` — numeric phi unusable on PG.
4. `cpp-dao-list-order-DEFECT` — PG pages skip/duplicate rows.
5. `java-jdbc-null-text-DEFECT` — Java can't read migrated rows.
6. `cpp-zmq-header-odr-DEFECT` — two ZMQ types in one TU don't compile.
7. `cpp-yaml-empty-mapping-DEFECT`, then `cpp-yaml-negative-map-keys-DEFECT`
   (same file, `harpia_yaml.h`).
8. `java-xml-byte-parity-DEFECT` — byte parity only, no wrong data.

## Index

| Doc | Status |
|---|---|
| [multi-system-reference/](multi-system-reference/README.md) | **Epics 1–4 shipped in V2 (2026-10-04)**: Java/Android hardened client, pooled DB servers, the three-program hardened reference system (`HarpiaTest/app_example/multi_system/`) and the load harness. **Open:** epic 5 `windows-verification` (real Windows `station`), delegated to the Windows session. |
| [feature-examples/](feature-examples/README.md) | **Partly shipped.** Fixture cleanup shipped 2026-08-24. The `worked-examples` epic (one small runnable example per generated feature + an index) — not started. |
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | Foundation F6 + Ground Rule 6 plumbing **shipped** 2026-08-23. The `doc-comment-coverage` epic (real per-template doc-comments) — **not started**, after `multi-system-reference`. |
| [ci-pipeline/](ci-pipeline/README.md) | **Scoped, not started.** GitHub Actions running the existing `Docker/run.sh pytest UnitTests/` suite on push/PR, plus image-layer caching. 2 tasks, both written. Highest leverage-per-effort of the open initiatives — no CI today means nothing independently re-verifies any "N passed" claim. |
| [python-target/](python-target/README.md) | **Shipped to `dev` 2026-10-05** (not yet on `main`): all 14 epics / 54 tasks, full Docker suite green. Language #3: full C++ compliance parity (DDS + CURVE/ZAP included), generation-time codegen under `<dest>/python/`, C++/Java/Python interop tests (`test_*_xlang3.py`, `test_dds_xlang.py`). Decisions + findings for review: [NEXT_SESSION.md](python-target/NEXT_SESSION.md) (items 1-48); the findings are the `*-DEFECT` rows below. |
| [cpp-yaml-empty-mapping-DEFECT/](cpp-yaml-empty-mapping-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). C++ `from_yaml("{}")` returns false, contrary to its own contract; all-default messages don't round-trip. 1 task, no golden move. |
| [cpp-yaml-negative-map-keys-DEFECT/](cpp-yaml-negative-map-keys-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). Negative int map keys (`-5:`) are misread as YAML sequence items, in C++ and the Python port alike. 2 tasks (C++, then Python mirror). |
| [cpp-dao-list-order-DEFECT/](cpp-dao-list-order-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). C++ DAO `list`/paginated `list` have no `ORDER BY` → unstable/overlapping pages on PostgreSQL. Moves goldens. 2 tasks (C++, Java check). |
| [cpp-pg-introspection-schema-DEFECT/](cpp-pg-introspection-schema-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). PG migration introspection ignores `table_schema` → same-named tables in other schemas leak into the diff (data-loss risk on shared DBs). Moves goldens. 1 task + 1 planning decision. |
| [cpp-key-store-permissions-DEFECT/](cpp-key-store-permissions-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). `LocalKeyProvider` writes the KEK store and `.shred` sidecar with umask bits (world-readable under `022`), in C++ and the Python port alike. 2 tasks (C++, then Python), no `golden/` move. |
| [cpp-phi-numeric-column-type-DEFECT/](cpp-phi-numeric-column-type-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). A numeric `phi` column keeps its numeric SQL type but stores `enc:v1:` text → rejected on PostgreSQL in every language. Moves goldens. 2 tasks (DDL, migration). |
| [cpp-zmq-header-odr-DEFECT/](cpp-zmq-header-odr-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). Every `zmq/*_zmq.h` defines `runtime_origin_id()` → two ZMQ message types can't be used in one C++ TU. Moves goldens. 1 task + 1 planning decision. |
| [java-jdbc-null-text-DEFECT/](java-jdbc-null-text-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). `JdbcBind.extract` NPEs on a NULL text column, so Java can't read rows that predate a C++/Python migration; DAO header omits child tables. Moves `golden_java/`. 2 tasks. |
| [java-xml-byte-parity-DEFECT/](java-xml-byte-parity-DEFECT/README.md) | **Defect, not started** (found by python-target 2026-10-04). Java XML differs from C++/Python bytes in 3 pinned ways (`<x/>`, unescaped quotes, float text); JSON only in whitespace (kept). Moves `golden_java/`. 1 task. |
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
