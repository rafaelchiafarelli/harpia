# python-target — handoff for the next session

Written 2026-10-04 at a milestone, mid-initiative. Delete this file when the
initiative ships (like the other initiatives' handoff notes).

## Where things stand

Updated 2026-10-04 (same session, later): epics 0-4 done.

| # | Epic | State |
|---|---|---|
| 0-4 | seam, foundation, serialization, database, crypto-phi | **done** |
| 6 | `py-zmq` | **done** (`PyZmq/`) |
| 7 | `py-events` | **done** (`PyEvents/`) |
| 5, 8-13 | the rest | not started; order in `epics/README.md` |

## Start here

1. Branch chain in this clone: `dev → features → python-target → epics →
   <epic> → tasks → <task>`. Every finished epic is merged into `epics`.
   For a new epic: `git checkout epics && git checkout -b <epic> &&
   git branch -f tasks <epic>`, then branch each task off `tasks`.
2. Next: 5 (`py-transports-http`) or 9 (`py-dds`); then 8, 10, 12, 11, 13. Python crypto runtimes are in
   `Crypto/runtime/python/` (constants in `Crypto/key_provider_common.py`);
   phi DAOs subclass `harpia_runtime.db.phi.PhiDao`.
3. Runtime unit tests load copied runtimes via `UnitTests/_py_runtime_load.py`
   (isolated `sys.modules`).

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
21. py-database/6: Python dbio import is all-or-nothing (parse everything first -> ValueError writes nothing; rows created in ONE transaction -> duplicate key rolls all back) and returns the row count; C++ returns false and keeps the rows it already created. Export formats byte-identical (XML) / line-parse-equal (NDJSON) to C++.
22. py-crypto-phi/1: Python crypto runtimes live in Crypto/runtime/python/ (like Compliance/runtime/python/audit_sink.py), path constants PY_*_MODULE/_RUNTIME_SRC/_DEPS in Crypto/key_provider_common.py; copying them into a generated project is deferred to task 4 (its contract: only when a phi column exists). Tests copy them via UnitTests/_py_runtime_load.py (isolated sys.modules).
23. py-crypto-phi/1: a Dek owns its bytearray and wipes it in __del__, so p.unwrap_dek(w).material is empty once the temporary Dek is collected -- documented (hold the Dek / copy with bytes()); kept because the task mandates wiping on __del__.
24. py-crypto-phi/2: Python LocalKeyProvider writes the KEK store with plain open() (umask perms), matching C++'s std::ofstream. ** C++ FINDING (observation) **: neither restricts the key-store / .shred file to 0600, so KEK material is world-readable under a 022 umask. Kept for parity (placeholder backend).
25. py-crypto-phi/3: decrypt_field returns "" when the opened bytes aren't valid UTF-8 (C++ returns the raw bytes); decrypt_field_ll saturates beyond 19 digits (avoids Python's int() digit-limit ValueError); frame hex validated strictly (bytes.fromhex would accept whitespace C++ rejects). Added decrypt_field_ll (C++ has it) beside the contract's _int/_float.
26. py-crypto-phi/4: ** C++ FINDING **: a numeric/enum phi column keeps its numeric SQL type in the shared DDL (Database.model), but the DAO stores enc:v1: TEXT in it. SQLite accepts it (type affinity); PostgreSQL rejects it (patient_vitals.heart_rate is double precision -> InvalidTextRepresentation), so phi numeric columns are unusable on PG in C++ (create returns false) and Python (raises). Not fixed (moves golden/ DDL); Python PG round trip for patient_vitals marked strict-xfail. C++ side inferred from the shared DDL + bound text, not run on PG.
27. py-crypto-phi/4: PhiDao audits at C++'s points: update/remove audit even when no row matched; a not-found read audits nothing; an FK child DAO is built from the connection only (default key provider + sink), as C++ `child_dao _c(db_)`.
28. py-events/2: event DAOs publish after the outermost transaction commits (contextvar-shared after-commit queue; dropped on rollback) -- C++ publishes inline but autocommits per statement. Like C++, an update that matched no row still publishes, and an FK child event DAO written through its parent publishes too.
29. py-zmq/2: ZAP is a hand-written REP loop, not zmq.auth.ThreadAuthenticator (cert dirs, no audit hook). ensure_running keys a WeakKeyDictionary on the context (id() reuse could fail open). The task's "key starting with #" can't occur for real keys (first Z85 digit <= 82, '#' is 84): parser tested with a synthetic token, live ZAP with a real key containing '#'.
30. py-transports-http/1: one pool for both dialects (no psycopg_pool). sqlite_pool verifies WAL like C++. Observed once in ~20 runs: 8x100 writers through a 4-pool hit 'database is locked' at the 5 s busy_timeout (unfair busy handler + slow fsync on WSL2/Docker); default stays 5000 ms (C++ parity), the stress test uses 20 s.
31. py-transports-http/2: REST mirrors C++ answers exactly, incl. 204 for PUT/DELETE of a missing row and 503 for a reconnect failure (task said 'any other error -> 500'; C++ answers 503 'db reconnect failed', kept). No fixture table declares pagination[size] (every C++ default is 0), so default paging is tested via register_crud directly.
32. py-transports-http/3 (task marked 'Decision needed'): no defusedxml dependency -- documents with <!DOCTYPE/<!ENTITY are refused before parsing (SOAP forbids DTDs; expat handlers refuse too), bounded by the router's 1 MiB body limit. The SOAP parser does no namespace processing (expat), matching tinyxml2, so undeclared prefixes are accepted like C++.
33. py-transports-http/5: Python gRPC mixed mode can't verify an optional client cert (grpcio's require_client_auth=False means don't-request): gRPC callers are anonymous in mixed mode, so protected messages are refused over gRPC there (fail-closed); HTTP mixed mode matches C++. Because the fixture has protected/open messages, its bring-ups bake EMIT_TLS even under a low-risk profile (as C++), so the flat-gate tests of tasks 2-4 now register bindings on plain servers (as the C++ tests do). The 'certless reaches open, not protected' check needs task 6's gates -- tested there.
34. py-transports-http/6: RBAC runtime = Compliance/runtime/python/rbac.py (-> harpia_runtime.rbac), transport gates in PyHttp/runtime/rbac_gates.py (-> harpia_runtime.rbac_gates), both copied only when some message is RBAC-gated (C++ any_rbac rule). Consequence of 33: the generated mixed-mode GrpcServer answers UNAUTHENTICATED for every RBAC-gated RPC even with a valid cert (fail-closed); the gRPC (role, op) matrix is proven on a client-cert-required server, and gRPC-vs-C++ parity is at the decide() level (REST+SOAP are compared against a live C++ HttpServer). Test harness: _py_cpp_parity.activate() now drops harpia_generated/harpia_runtime from sys.modules when a test switches generated project (hardened vs low-risk now differ; a full-suite run would otherwise reuse the first one imported).
35. py-transports-http/7: Python verify() returns (Verdict, Claims | None) (no out-param); RevocationList content stamp is sha256 (C++ uses an internal HMAC -- private, not part of the format). Bearer tokens make RBAC usable over the Python mixed-mode gRPC server (token from HTTPS POST /session; heartBeat can't issue there, item 33). Client helper = harpia_runtime.session_client (copied with the RBAC runtimes).
36. py-dds/3: the governance/permissions/selection documents are COPIED into python/harpia_generated/dds/security/ (not referenced), written by DdsAdapter.write_security_documents (extracted from _write_security; C++ golden unchanged) because the python stages run before the C++ ones. secured_participant also refuses a domain id that already exists in the process (Cyclone would reuse its possibly-plaintext config). Python secured peers run one per process in tests (domain config is per process).
37. py-versioning/1: the Python GrpcServer registers the capability service (task contract); the C++ GrpcServer does not (C++ users register capabilities_service themselves) -- additive divergence, documented in PyCapability/CLAUDE.md.
38. py-versioning/3: wire-number freeze holds for Python (no violation). Observation (not a FieldMap bug, no stop): a retired number lives only in the sidecar's `# reserved:` line -- the emitted .proto carries no `reserved N;` statement, so the generator never reuses it but protoc wouldn't stop a hand edit that did. Same for every target.
39. py-tests/2: the generated REST/SOAP bodies serve the per-message register()s on a plain in-process router (testing.serve), like the C++ tests' Crow app -- not the generated mTLS HttpServer (the fixture's protected/open messages make it TLS-only). RBAC bodies are fail-closed checks only (C++ split).
40. ** py-zmq FIX ** (found by py-tests/2's low-risk run): harpia_runtime.zap was copied only under a hardened profile, but zmq.py imports it (lazily) -> a low-risk generated tree failed mypy --strict. zap.py + audit sink now ship with zmq.py under every profile (inert unless zap=True).
41. py-artifacts/1: the generated Python project is an SBOM *component* (type application, pypi:harpia-generated), not a metadata.component sub-entry. A PyPI range has no single version: the component version is the declared range string and its purl names the package only (pkg:pypi/protobuf); exact pins (cyclonedds==0.10.5) get a versioned purl. Pins moved to PyAdapter/dependencies.py (renders pyproject.toml byte-identically + feeds the SBOM).
