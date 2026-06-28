# harpia tests

## Golden-file harness

`test_golden.py` runs the front-end pipeline on `HarpiaTest/test.harpia` and
asserts the intermediate artifacts have not drifted from the committed snapshots
in `tests/golden/`:

| artifact | what it captures |
|----------|------------------|
| `tokens.txt`   | the token stream after comment + import removal |
| `messages.txt` | the `Message` objects built by `MessageCreator` |
| `proto/*.proto`| every emitted proto (message + gRPC service) |

The snapshots are keyed by the input's md5 hash (`734126ee...`), which is stable
as long as `test.harpia` and its includes are unchanged.

## Stage 7 (protoc -> C++)

`test_stage7.py` runs the front-end, then `ProtoCompiler` (Stage 7), and asserts
protoc emits one `.pb.h`/`.pb.cc` per input proto **and** that every generated
`.pb.cc` compiles with g++. It is skipped automatically when `protoc` is not on
PATH, so it only really exercises inside the Docker toolchain.

### Running (Docker -- recommended)

The whole toolchain (Python, protoc, gRPC, CMake, g++, pytest) lives in the
image; nothing is installed on the host. The helper runs as your UID so any
generated files stay owned by you:

```sh
docker/run.sh pytest          # full suite incl. Stage 7
docker/run.sh python3 main.py # full pipeline incl. C++ generation
docker/run.sh                 # interactive shell
```

### Running (host, no protoc)

The system Python has no pip; use a venv. Stage 7 will be skipped.

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

### Updating snapshots after an intentional change

```sh
HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_golden.py
git diff tests/golden     # review the drift -- this review is the point
```

`run_pipeline.py` is the standalone harness that produces the artifacts; the
test invokes it in a fresh subprocess (LexicalAnalyzer accumulates tokens in
class-level state, so a clean interpreter per run is required).
