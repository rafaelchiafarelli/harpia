# harpia tests

All tests run the generator on `HarpiaTest/test.harpia` and check the result.
Two kinds:

- **Golden-file** (`test_golden.py`) — snapshots every intermediate artifact so
  any change to the pipeline shows up as a reviewable diff. Pure Python.
- **Per-stage behavioural** — actually compile/link/run the generated C++ to
  prove each back-end works. These need the C++ toolchain and are **skipped**
  automatically when it is absent, so the host suite stays green; they run fully
  inside the Docker image.

## Running (Docker — recommended)

The whole toolchain (Python, protoc, gRPC, CMake, g++, ZMQ, pytest) lives in the
image; nothing is installed on the host. The helper runs as your UID so any
generated files stay owned by you:

```sh
docker/run.sh pytest           # full suite
docker/run.sh python3 main.py  # full pipeline (writes HarpiaTest/test_build/)
docker/run.sh                  # interactive shell
```

## Running (host, no toolchain)

The system Python has no pip; use a venv. The compile/run tests are skipped.

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

## Test files

| file | what it checks | needs |
|------|----------------|-------|
| `test_golden.py`      | tokens, messages, generated `proto/`, `json/`, `zmq/`, `xml/` wrappers and the `sidecars/` (sql/modifier/access/pswd) match `tests/golden/` | python only |
| `test_frontend.py`    | front-end error paths (bad import, unbalanced braces, malformed `map<>`, nameless message, lexer mismatch, …) return the right `Error` type | python only |
| `test_stage7.py`      | Stage 7: `protoc` emits one `.pb.{h,cc}` per proto and every `.pb.cc` compiles | protoc, g++ |
| `test_stage9.py`      | Stage 9: JSON adapters compile and a real JSON round-trip runs | protoc, g++ |
| `test_stage13.py`     | Stage 13 gRPC: every `*_service.grpc.pb.cc` compiles, and a Stub + Service skeleton link and run | protoc, grpc_cpp_plugin, g++ |
| `test_stage13_zmq.py` | Stage 13 ZMQ: transports compile and a PUSH/PULL round-trip runs over a real socket (incl. the stamped originator id) | protoc, g++, libzmq |
| `test_stage10_xml.py` | Stage 10: XML adapters compile, `to_xml`/`from_xml` round-trip, XSD is well-formed | protoc, g++ (uses vendored tinyxml2) |
| `test_stage8_db.py`   | Stage 8: generated SQL schema executes in SQLite; CRUDL DAO round-trip (insert→read→update→list→delete); DB↔JSON/XML bulk export/import round-trip | cc + g++ (vendored sqlite); CRUDL/IO parts also protoc |
| `test_stage12_rest.py`| Stage 12: REST bindings serve real HTTP CRUD (POST→GET/:id→list→PUT→DELETE→404) against an httplib server backed by SQLite | protoc, cc, g++ (vendored sqlite + cpp-httplib) |
| `test_demo.py`        | end-to-end: build the generated project with its own CMake and run client→server, asserting the message crosses | cmake, protoc, grpc_cpp_plugin, g++, libzmq |

`run_pipeline.py` and `run_frontend.py` are standalone harnesses the tests drive
in a fresh subprocess (LexicalAnalyzer accumulates tokens in class-level state,
so a clean interpreter per run is required).

## Golden artifacts

Snapshots live under `tests/golden/`, keyed by the input's md5 hash
(`734126ee…`, stable while `test.harpia` and its includes are unchanged):

| artifact | what it captures |
|----------|------------------|
| `tokens.txt`   | token stream after comment + import removal |
| `messages.txt` | the `Message` objects built by `MessageCreator` |
| `proto/`       | every emitted `.proto` (message + gRPC service) |
| `json/`        | every JSON adapter header (Stage 9) |
| `zmq/`         | every ZMQ transport header (Stage 13) |
| `xml/`         | every XML adapter wrapper (Stage 10) |
| `db/`          | every CRUDL DAO header (Stage 8) |
| `dbio/`        | every DB↔JSON/XML import/export header (Stage 8) |
| `rest/`        | every REST binding header (Stage 12) |
| `sidecars/`    | per-message SQL schema + modifier/access/password flag files |

### Updating snapshots after an intentional change

```sh
HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_golden.py
git diff tests/golden     # review the drift -- this review is the point
```
