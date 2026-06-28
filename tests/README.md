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

### Running

The system Python has no pip; use a venv:

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/test_golden.py
```

### Updating snapshots after an intentional change

```sh
HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_golden.py
git diff tests/golden     # review the drift -- this review is the point
```

`run_pipeline.py` is the standalone harness that produces the artifacts; the
test invokes it in a fresh subprocess (LexicalAnalyzer accumulates tokens in
class-level state, so a clean interpreter per run is required).
