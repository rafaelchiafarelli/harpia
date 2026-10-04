# PyAdapter — the Python target's project layout + generation-time protoc

**Pipeline role / purpose:** The first stage of the `python` language backend
(`LangBackend/python.py`, `HARPIA_GEN_LANG=python`). Emits one installable
project under `<dest>/python/` and compiles the schema's protos into Python
modules at generation time (like C++, not at build time like Java).

**Entry point:** `PyAdapter(messages, dest, compliance).Process()`, called by
`PythonBackend.run_python`. Returns `None` or a non-fatal `Error`.

**Output (`<dest>/python/`):**
- `pyproject.toml` — project `harpia-generated`, `requires-python >= 3.10`,
  deps `protobuf>=4.21.12,<5` + `grpcio>=1.51.1,<2`, extras `zmq` / `postgres`
  / `dds` (ranges match the image's pins, `Dockerfile` header).
- `harpia_runtime/`, `harpia_generated/` (+ `py.typed`) — copied verbatim
  from `PyAdapter/runtime/` (`__pycache__` skipped). Later epics add runtime
  modules under `runtime/harpia_runtime/<concern>/`.
- `proto/harpia_generated/protofiles/*.proto` — every per-message `.proto`
  and `_service.proto` plus `errorCode` / `heartBeat` /
  `capabilities_service`, with `import "protofiles/…"` rewritten to
  `import "harpia_generated/protofiles/…"` (`rewrite_proto_imports`).
- `harpia_generated/protofiles/<x>_pb2.py` + `<x>_pb2.pyi`, and
  `<x>_pb2_grpc.py` only for protos that declare a `service` (the plugin
  emits one per input; the rest are dropped).

## `PyDocsAdapter.py` — Sphinx skeleton (py-foundation task 3)
- Writes `<dest>/python/docs/{conf.py,index.rst,api.rst}`: autodoc +
  napoleon (Google-style docstrings), one `automodule` per harpia-written
  module under `harpia_runtime` / `harpia_generated` (`discover_modules`,
  protoc output skipped). Runs **last** among the Python stages
  (`PythonBackend.run_python`), so every later epic's modules are documented
  with no extra wiring — they only need docstrings (Ground Rule 6).
- The landing page **links** to `USAGE_EXCERPT.md` (the C++ pipeline's
  Doxygen excerpt of USAGE.md §5/§7/§16) instead of embedding it: Sphinx
  needs `myst-parser` for Markdown, which the image doesn't carry.

## Quality gate (every Python epic keeps it green)
From `<dest>/python/`: `mypy` (config `[tool.mypy]`, `strict = true`,
`files = harpia_runtime, harpia_generated`), `ruff check .` (`E,F,W,I,B,UP`,
py310, protoc output excluded) and `sphinx-build -W docs <out>`.
- `harpia_generated.protofiles.*` has `ignore_errors = true`: it is all protoc
  output. `_pb2.py` is typed through its `.pyi` (mypy prefers the stub);
  `_pb2_grpc.py` is untyped grpc_python_plugin code. Decision recorded at
  task 3: ignore errors there rather than exclude, so importing modules still
  resolve the types.
- `grpc` / `grpc.*` get `ignore_missing_imports` (grpcio ships no types).
  Later epics add the same for any untyped dependency they import.

## Key facts / gotchas
- **Import path decision (task 2, option (b)):** protos are re-rooted under
  `harpia_generated/protofiles/`, so modules import as
  `from harpia_generated.protofiles import x_pb2`. No generic top-level
  `protofiles` package to collide in a consumer's environment. Only the
  descriptor-pool *file names* differ from C++/Java; proto packages and
  message names are unchanged, so the wire bytes are identical (checked
  against the C++ class in `UnitTests/test_python_codegen.py`).
- Codegen uses the **system** `protoc` (`--python_out --pyi_out`) and
  `grpc_python_plugin` from `protobuf-compiler-grpc` (`--grpc_python_out`),
  never grpc_tools' bundled protoc. Missing either is a non-fatal
  `PROTOC_NOT_FOUND`; the layout is still written.
- protoc output is compiled into a scratch dir and diff-copied
  (`copy_tree_if_different`), so an unchanged module keeps its mtime.
- `<name>_<hash>_pb2*.py` match `Util.util._NAME_HASH_RE`, so a renamed
  message's modules are pruned by `prune_stale_outputs` for free.

## Touchpoints
- Depends on: the front end's `<dest>/proto/protofiles/` (FileCreator +
  `copyBasicProtos`), `Util.util`.
- Tested by: `UnitTests/test_python_quality_gate.py` (the gate + negative
  controls), `UnitTests/test_golden_python.py` (`UnitTests/golden_python/`,
  protoc output not snapshotted), `UnitTests/test_python_codegen.py`.
