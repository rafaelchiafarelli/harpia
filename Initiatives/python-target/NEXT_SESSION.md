# python-target — handoff for the next session

Written 2026-10-04 at a milestone, mid-initiative. Delete this file when the
initiative ships (like the other initiatives' handoff notes).

## Where things stand

| # | Epic | State |
|---|---|---|
| 0 | `lang-backend-seam` | **done** (`epics/lang-backend-seam-done/`) |
| 1 | `py-foundation` | **done** (`epics/py-foundation-done/`) |
| 2 | `py-serialization` | **done** (`epics/py-serialization-done/`) |
| 4 | `py-database` | **in progress**: tasks 1, 2a, 2b, 2c, 3, 4, 5a done (`-done` files); **next: 5b, then 6** |
| 3, 5-13 | the rest | not started; order in `epics/README.md` (do `py-crypto-phi` (3) after `py-database`: its task 4 needs the DAOs) |

## Start here

1. Branch chain in this clone: `dev → features → python-target → epics →
   py-database → tasks → <task>`. `tasks` holds every finished py-database
   task; nothing of py-database is merged into `py-database`/`epics` yet
   (that happens when the epic is done).
2. `git checkout tasks && git checkout -b 5b-migration-child-tables`, then
   implement `epics/py-database/tasks/5b-migration-child-tables.md`.
   Groundwork already in place for it:
   - `Database/backends` already has the child plans (`rep_child_plan`,
     `map_child_plan`, `composed_child_plan`) and the engine
     (`PyDatabase/runtime/migrate.py`) already runs child renames, the reap
     and child plans; 5a just emits them inert
     (`child_renames=()`, `child_current=None`, `child_plans=()` in
     `PyDatabaseAdapter._render_migration`). 5b fills those three from
     `Database/MigrationAdapter._render`'s child logic (renamable set,
     `child_table_names`, `int_type` as the owner type, like C++).
   - Test pattern: `UnitTests/test_py_db_migrate.py` (hand-built older
     SQLite states + a C++ migrate binary, compare end states) and
     `test_python_db_postgres.py::test_migrate_on_postgres`.
3. Then task 6 (`dbio-json-xml`), then close the epic: merge `tasks →
   py-database`, `git mv epics/py-database epics/py-database-done`, merge
   `py-database → epics`.

## Run rules Rafael set for this initiative (2026-10-04)

- **Decide, log, continue** on undeclared deps / ambiguous contracts: pick
  the most conservative option, record it in the commit message and the
  module `CLAUDE.md`, append it to the log below. Still a hard STOP for
  anything that compromises the library's integrity or moves `golden/`
  (C++) / `golden_java/` bytes without the task saying so.
- **Full Docker suite only at the end** of the initiative (not run since V2).
  Per task: the task's own tests + `test_golden*.py` +
  `test_python_quality_gate.py`.

## How each task has been done (keep doing it this way)

- Implement → run the quality gate on the generated tree → update
  `UnitTests/golden_python/` (`HARPIA_UPDATE_GOLDEN=1 pytest
  UnitTests/test_golden_python.py -k matches`, review the diff) → task tests
  in Docker → module `CLAUDE.md` + `UnitTests/CLAUDE.md` entry → commit →
  `git mv` the task file to `-done` in a second commit → `--no-ff` merge into
  `tasks` → branch the next task.
- Quality gate on the generated tree (inside `Docker/run.sh bash -c ...`):
  regenerate with `HARPIA_GEN_LANG=python HARPIA_OUTPUT_DIR=/tmp/pg python3
  main.py`, `ruff check --fix --config /tmp/pg/python/pyproject.toml
  <runtime source dirs>`, regenerate, then in `/tmp/pg/python`: `mypy
  --no-incremental` and `ruff check --no-cache .`.
- Hand-written Python runtimes live next to their adapter
  (`PyAdapter/runtime/`, `PySerialization/runtime/`, `PyDatabase/runtime/`,
  `Compliance/runtime/python/`) and are copied with
  `PyAdapter.runtime_copy.copy_runtime_module`.
- Cross-language parity harness: `UnitTests/_py_cpp_parity.py` (`probe` for
  serialization ops, `dao_probe`/`cpp_dao` for SOCI DAOs, `populate`,
  `fixture_messages`).

## Decisions & findings log (for Rafael's end-of-run review)

Items marked **C++ FINDING / C++ BUG** are pre-existing C++ issues found
while porting; the C++ code was not changed.

# python-target one-go run — decisions & findings log
1. lang-backend-seam/3: unknown HARPIA_GEN_LANG is now a hard error (resolved before the output dir is created); used to silently fall back to C++-only.
2. Seam: java and python are additive on top of C++ (JavaBackend/PythonBackend subclass CppBackend).
3. py-foundation/1: grpc_python_plugin (protobuf-compiler-grpc 1.51.1) instead of apt python3-grpc-tools (1.14.1, bundles protoc 3.6).
4. py-foundation/1: mypy-protobuf from apt (3.2.0), not pip; added pip pin types-protobuf==4.21.0.7 (mypy --strict needs it).
5. py-foundation/2: _pb2 import path option (b): protos re-rooted under harpia_generated/protofiles/, imports rewritten. Wire bytes == C++.
6. py-foundation/2: golden_python excludes protoc output (*_pb2*.py/.pyi), like C++ goldens exclude .pb.h.
7. py-foundation/3: Sphinx landing page LINKS USAGE_EXCERPT.md (no myst-parser in image).
8. py-foundation/3: mypy ignore_errors on harpia_generated.protofiles.*; grpc ignore_missing_imports.
9. py-foundation/4: Python runtimes are copied on demand via PyAdapter.runtime_copy.copy_runtime_module (C++ copy_if_different idiom); audit_sink source in Compliance/runtime/python/.
10. py-serialization/1: JSON byte-identical to C++ after escaping '<' '>' as </> like C++.
11. py-serialization/3: from_yaml("{}") returns True in Python (task spec + C++ header comment), C++ CODE returns false. ** C++ BUG for Rafael **
12. py-serialization/3: negative integer map keys don't round-trip through YAML in C++ or Python ('-5:' reads as a sequence item). ** C++ BUG for Rafael **; parity fixture uses non-negative map keys.
13. py-serialization/4: redacted XML/YAML read back: numeric phi fields -> default, but a STRING phi field reads the literal placeholder '[REDACTED]' (task text said 'default'; this is what C++ does too, ported as-is).
14. py-database/1: DbBackend.param_placeholder() added to the shared backend (option (a)); ? sqlite3, %s psycopg.
15. py-database/2a: ruff E501 ignored for harpia_generated/** only (generated SQL on one line); hand-written runtimes keep the 88-col limit.
16. py-database/3: Python list()/list(offset,limit) ORDER BY the primary key. ** C++ FINDING **: the C++ DAO's list/paginated list has no ORDER BY -> unstable pages on PostgreSQL (SQLite happens to return rowid=pk order).
17. py-database/5a: DbBackend gains SQL-level migration PLANS (retype_plan, rep_child_plan, map_child_plan, composed_child_plan, drop_column_sql). The C++ *_dynamic methods were refactored to build their SQL through the same private helpers -> C++ output proven byte-identical (goldens + old-vs-new comparison, both dialects).
18. py-database/5a: Python migration = one transaction (explicit BEGIN on sqlite3 so DDL rolls back); errors raise (C++ returns false).
19. ** C++ FINDING **: PostgreSQL migration introspection (information_schema.columns/tables) is not schema-qualified, in C++ and Python alike -> same-named tables in another schema leak into the diff. Python PG migration test uses a throwaway DATABASE.
20. py-database/5b: the "g++-gated C++-v1 -> Python-v2 case with a map field" is the hand-built older state (as test_stage8_db.py does: no v1 generator exists) migrated by C++ and by Python, end states compared; map renames/retypes included.
