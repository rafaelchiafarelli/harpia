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
  intermediate artifacts (tokens, messages, proto/, json/, zmq/, grpc/, xml/,
  db/, migrate/, dbio/, rest/, soap/, wsdl/, gen_tests/, sidecars/) into an output
  dir for snapshotting. `python3 tests/run_pipeline.py <output_dir>`. **rmtrees
  `<output_dir>/build` on every run.**
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
- `test_stage7.py` — protoc emits/compiles `.pb.{h,cc}`. (protoc, g++)
- `test_stage8_db.py` — SQL schema, CRUDL round-trip, FK, repeated-FK link table,
  map<K,V>, repeated scalar, migration, DB↔JSON/XML. (cc + g++, some protoc)
- `test_stage9.py` — JSON adapters compile + round-trip. (protoc, g++)
- `test_stage10_xml.py` — XML adapters compile, to/from_xml round-trip, XSD.
- `test_stage11_soap.py` — SOAP-over-HTTP endpoint (credential gate).
- `test_stage12_rest.py` — REST HTTP CRUD, credential-gated.
- `test_stage13.py` — gRPC services compile, CRUDL-backed impl, metadata auth.
- `test_stage13_zmq.py` — ZMQ PUSH/PULL round-trip over a real socket.
- `test_stage14.py` — every generated `*_test.cpp` compiles/runs green; CTest
  wiring; `cmake -DHARPIA_BUILD_TESTS=ON` + `ctest`.
- `test_demo.py` — end-to-end: build generated project with its own CMake, run
  client→server. (cmake, protoc, grpc_cpp_plugin, g++, libzmq)

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
`messages.txt`; dirs: `proto/`, `json/`, `zmq/`, `grpc/`, `xml/`, `db/`,
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

## Touchpoints
- Depends on: the whole generator (all adapters + front-end), `HarpiaTest/`
  fixtures, repo `third_party/` (vendored sqlite/tinyxml2/cpp-httplib).
