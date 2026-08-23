# tests — the pytest suite for the generator itself

**Pipeline role / purpose:** Verifies the harpia generator, not generated user
code. Two kinds: (1) golden-file snapshot tests (pure Python, always run) and
(2) per-stage behavioural tests that actually compile/link/run the generated
C++ (skipped automatically when the C++ toolchain is absent; run fully in Docker).

**Entry points / how to run:**
- Docker (recommended, full toolchain): `docker/run.sh pytest`.
- Host (no toolchain, compile/run tests skip): `python3 -m venv .venv &&
  .venv/bin/pip install pytest && .venv/bin/python -m pytest`.
- Update golden snapshots after an intentional change:
  `HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_golden.py`
  then review `git diff tests/golden` (the review is the point).

**Inputs → Outputs:** all tests run the generator on `HarpiaTest/test.harpia`
(+ its `Include/`), via the harnesses, and compare/compile the result.

## Harnesses (standalone, driven in a fresh subprocess)
- `run_pipeline.py` — mirrors `main.py`'s full orchestration, then dumps the
  intermediate artifacts (tokens, messages, proto/, json/, zmq/, grpc/,
  capability/, xml/, db/, migrate/, dbio/, rest/, soap/, wsdl/, gen_tests/,
  sidecars/) into an output
  dir for snapshotting. `python3 tests/run_pipeline.py <output_dir>`. **rmtrees
  `<output_dir>/build` on every run.** Also loads a `ComplianceContext` (via
  `Compliance.context.load_compliance_context`, honoring
  `HARPIA_COMPLIANCE_CONFIG` same as `main.py`) and threads it into every
  stage constructor, recording a per-stage `instance.compliance is
  compliance` check into `compliance_smoke.txt` -- `test_compliance.py`'s
  integration test reads this back.
- `run_frontend.py` — runs only the front-end (pre_lex → lexer → MessageCreator)
  on one file and prints `RESULT PRELEX/LEX/MSG <ErrorType>` or `RESULT OK`.
  `python3 tests/run_frontend.py <file> <dest>`.
- Both run in a **fresh process** because `LexicalAnalyzer` accumulates tokens in
  class-level state — a clean interpreter per run is required. Tests invoke them
  via `subprocess`.

## Test files
- `test_golden.py` — snapshots every intermediate artifact vs `tests/golden/`.
  Python only. Honors `HARPIA_UPDATE_GOLDEN=1` to rewrite snapshots.
- `test_frontend.py` — front-end error paths return the right `Error` type.
  Python only.
- `test_compliance.py` — Foundation F1's `Compliance/context.py`: missing
  config / omitted field falls back to the strictest profile per-field; a
  fully-specified config parses; an unknown/invalid enum value or a
  malformed `jurisdiction` list is a hard `ComplianceConfigError`, never
  silently defaulted; `HARPIA_COMPLIANCE_CONFIG` env override. Integration:
  runs the real pipeline (`run_pipeline.py`, with a compliance config
  present) and reads back `compliance_smoke.txt` (a per-stage marker
  `run_pipeline.py` emits recording `instance.compliance is <the loaded
  ComplianceContext>` for every stage constructed) to confirm the exact
  object reached every one, not just a default. Pure Python.
- `test_stage7.py` — protoc emits/compiles `.pb.{h,cc}`. (protoc, g++)
- `test_stage8_db.py` — SQL schema, CRUDL round-trip, FK, repeated-FK link table,
  map<K,V>, repeated scalar, migration, DB↔JSON/XML. (cc + g++, some protoc)
- `test_stage9.py` — JSON adapters compile + round-trip. (protoc, g++)
- `test_stage10_xml.py` — XML adapters compile, to/from_xml round-trip, XSD.
- `test_stage11_soap.py` — SOAP-over-HTTP endpoint (credential gate).
- `test_stage12_rest.py` — REST HTTP CRUD, credential-gated.
- `test_stage13.py` — gRPC services compile, CRUDL-backed impl, metadata auth.
- `test_fieldmap.py` — field-identity (wire-number freeze) unit tests, from the message-versioning effort: `message.FieldMap.freeze`
  driven directly (no lexer) — first-generation freeze, reorder/insert
  stability, delete-retires-number, rename-keeps-number, unresolvable-rename
  falls back (mirrors `Database/MigrationAdapter`'s conditional RENAME),
  hidden-field (`ID_`/`STATUS_`/`ERROR_`/`ORIGINATOR`) stability across an
  md5 hash change, reserved-number-reuse hard error, sidecar path shape.
  Pure Python.
- `test_fieldmap_frontend.py` — the same §3 reorder/delete properties but
  through the real front-end pipeline (`run_frontend.py`, fresh subprocess
  per generation), confirming `message/Message.py`'s wiring actually calls
  `FieldMap.freeze`, not just the module in isolation. Pure Python.
- `test_message_versioning_wire.py` — §3's integration test: two real
  generations of one root `.harpia` file (same schema_registry sidecar),
  the second reordering fields and adding one; compiles gen1's protobuf
  class into a "writer" program and gen2's into a separate "reader",
  proving a real serialized message survives the reorder. (protoc, g++)
- `test_message_versioning_parse_boundary.py` — §4: JSON tolerates an
  unrecognized key (`ignore_unknown_fields`); an `optional`-tagged field's
  `has_<field>()` distinguishes "never set" from "explicitly set to the
  zero value" through both the protobuf binary and XML round trip (the
  latter proving the `harpia_xml.h` `has_presence()` fix specifically); a
  newer schema's added field, written by a "new" binary, parses cleanly on
  an "old" binary that never heard of it (inverse direction of
  `test_message_versioning_wire.py`). (protoc, g++)
- `test_message_versioning_capability.py` — §5's gRPC capability handshake:
  `harpia::capability::negotiate()` gets a real server's advertised
  message-type set over an in-process channel; a peer with other services
  registered but not `capabilities_service` (a genuine pre-feature legacy
  peer) resolves to the named "legacy peer" outcome, not a hang;
  `harpia::capability::Dispatcher` (shared, transport-agnostic -- tested
  once here, not per transport) routes a covered type to its handler and
  falls back (never silently) for an uncovered type or a covered type with
  no registered handler. (protoc, grpc_cpp_plugin, g++)
- `test_message_versioning_capability_http.py` — §5's REST/SOAP capability
  handshake (shared: both ride the same `crow::SimpleApp`): a real Crow
  server's `GET /capabilities` route answers `negotiate()` correctly; a real
  server with other routes but no `/capabilities` (legacy peer) and an
  unreachable host both resolve to the named legacy-peer outcome. The two
  Crow-server cases currently FAIL in this Docker image for the same
  pre-existing, unrelated reason as `test_stage11_soap.py`/
  `test_stage12_rest.py` (`third_party/asio` is missing
  `asio/detail/bind_handler.hpp`) -- the third case (`negotiate()` against
  an unreachable host, no Crow involved) passes, and the Crow-dependent
  logic was separately verified against a local `crow.h` stub isolating it
  from the asio gap; see `HttpCapabilityAdapter/CLAUDE.md`. (protoc, g++, cc)
- `test_message_versioning_capability_zmq.py` — §5's ZMQ capability
  handshake: a real REQ/REP round trip (`capabilities_responder` +
  `negotiate()`) over `inproc://`; a real `tcp://` port with nothing
  listening resolves to the named legacy-peer outcome within the deadline,
  not a hang. No `crow.h`/asio dependency, so unaffected by the gap above --
  both tests pass. (protoc, g++, libzmq, cppzmq)
- `test_stage13_zmq.py` — ZMQ PUSH/PULL round-trip over a real socket, plus a
  CURVE round-trip over real `tcp://` (matching keys succeed, a wrong server
  public key times out -- CURVE is a no-op over `inproc`, which the other
  tests here use, so this one needs a real handshake).
- `test_stage14.py` — every generated `*_test.cpp` compiles/runs green; CTest
  wiring; `cmake -DHARPIA_BUILD_TESTS=ON` + `ctest`.
- `test_stage8_pg.py` — **opt-in** live-PostgreSQL CRUDL round-trip (generates with
  `HARPIA_DB_BACKEND=postgresql`); skipped unless `HARPIA_PG_DSN` points at a
  reachable server.
- `test_consumer_example.py` — downstream-consumption contract: builds + runs
  `examples/consumer/` against a freshly generated project
  (`cmake -DHARPIA_GEN=<gen>`), asserting the black-box wiring still works.
  Also builds/runs it with `-DUSE_TLS=ON` and does a real TLS handshake
  (`ssl.get_server_certificate`) against the running server.
- `test_incremental_regen.py` — regeneration is write-if-different, not a
  blanket wipe (see `Util.util.write_if_different`/`prune_stale_outputs`,
  `main.py`). Runs the pipeline twice against the *same* persistent output
  dir (the only place in the suite that does): once with unchanged input,
  asserting a generated file's mtime doesn't move; once renaming a message
  between runs (root file's own text unchanged, so its hash stays stable —
  the normal `Include/`-editing workflow), asserting the old name's output
  is pruned. Uses a tiny inline two-file fixture, not the shared
  `HarpiaTest/Include` ones, so it doesn't touch the pinned `HASH` below.
- `test_atomic_write.py` — crash-safety of `write_if_different`/
  `copy_if_different`: simulates a kill between the temp-file write and the
  atomic rename (`os.replace` monkeypatched to raise) and asserts the
  destination is left exactly as it was, with no leftover temp file. Pure
  Python.
- `test_demo.py` — end-to-end: build generated project with its own CMake, run
  client→server. (cmake, protoc, grpc_cpp_plugin, g++, libzmq) Also builds and
  runs it a second time with `-DUSE_ZMQ_CURVE=ON` (over `ipc://`, which -- like
  `tcp://` -- goes through the real ZMTP handshake), confirming the ephemeral
  keypairs the configure-time keygen probe writes actually match between the
  server and client binaries from the same build.

## The pinned HASH constant — matters for the multi-root feature
`test.harpia` (and its includes) hash to an md5 the generator uses to key every
emitted filename. It is currently **`c96f8fd7f45108efee5a8ecb43eab1da`**, pinned as
a top-of-file `HASH = "..."` constant in exactly these SIX files:
- `test_stage8_db.py`
- `test_stage10_xml.py`
- `test_stage11_soap.py`
- `test_stage12_rest.py`
- `test_stage13.py`
- `test_stage13_zmq.py`

If `test.harpia` or any of its includes change, this hash changes and **all six
constants must be bumped in lockstep** (the tests build header/filenames from it).
The other test files derive the hash at runtime instead of pinning it.
(Note: the README's mention of `734126ee…` is stale prose — the live golden hash
is `c96f8fd7…`, as seen in `tests/golden/db/` and `tests/golden/gen_tests/`
filenames.)

## Golden snapshots (tests/golden/)
Committed reference output keyed by the input hash. Files: `tokens.txt`,
`messages.txt`; dirs: `proto/`, `json/`, `zmq/`, `grpc/`, `capability/`
(whole-project gRPC/HTTP/ZMQ capability advertisements, S5), `xml/`, `db/`,
`migrate/`, `dbio/`, `rest/`, `soap/`, `wsdl/`, `gen_tests/` (generated unit tests
+ CTest CMakeLists), `sidecars/` (per-message SQL schema + modifier/access/pswd
flag files, subdirs `database/ modifier/ access_modifier/ database_access/`).
Do not hand-edit — regenerate via `HARPIA_UPDATE_GOLDEN=1` and review the diff.

## Key facts / gotchas
- Behavioural tests use `pytest.mark.skipif(shutil.which(...) is None, ...)` per
  required tool, so a bare host stays green; Docker has the full toolchain.
- Docker non-TTY gotcha: `docker/run.sh` runs as your UID so generated files stay
  yours; don't pass `-it` in non-interactive/CI contexts.
- `run_pipeline.py` rmtrees its `build/` subdir each run — never point it at a dir
  whose `build/` you want to keep.
- **Pre-existing, unrelated known-failing group (7 tests as of 2026-08-22,
  9 as of 2026-08-23 once `test_message_versioning_capability_http.py`'s two
  Crow-server cases joined it):** `test_consumer_example.py` (both),
  `test_stage11_soap.py`, `test_stage12_rest.py` (both), `test_stage14.py`
  (both), and the two Crow-dependent cases in
  `test_message_versioning_capability_http.py` all fail in this Docker
  image because `third_party/asio` is missing
  `asio/detail/bind_handler.hpp` -- anything that `#include`s `crow.h`
  (which pulls in `asio.hpp`) fails to compile. Confirmed pre-existing via
  `git stash` against a clean checkout, not caused by message-versioning
  work. A real, separate fix (out of message-versioning's scope) would
  properly re-vendor `third_party/asio`.

## Touchpoints
- Depends on: the whole generator (all adapters + front-end), `HarpiaTest/`
  fixtures, repo `third_party/` (vendored sqlite/tinyxml2/crow/asio), the
  HTTP test client `tests/harpia_test_client.h`, and `Compliance.context`
  (Foundation F1).
