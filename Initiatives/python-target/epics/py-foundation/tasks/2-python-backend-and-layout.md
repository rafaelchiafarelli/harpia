## `python` LangBackend, `<dest>/python/` layout, generation-time protoc, golden baseline

- **Depends on:** `lang-backend-seam` (all 3 tasks), task 1.
- **Contract:**
  - `HARPIA_GEN_LANG=python` resolves to a `python` backend registered in
    the seam's registry. No change to the `cpp`/`java` backend classes.
    Whether the C++ pipeline also runs for `python` follows whatever
    `lang-backend-seam` task 3 recorded for `java` (today Java is additive
    on top of C++). Apply the same rule; don't invent a different one.
  - A new adapter package `PyAdapter/` (name follows the `GradleAdapter`
    precedent; adjust if task 3 of the seam fixed a naming scheme) emits:
    - `<dest>/python/pyproject.toml`: project `harpia-generated`, Python
      `>=3.10`, runtime deps declared with ranges matching task 1's
      versions; `[tool.mypy]` and `[tool.ruff]` sections (populated by
      task 3).
    - `harpia_runtime/__init__.py` and `harpia_generated/__init__.py`:
      two top-level packages, neither colliding with any harpia source
      package name.
    - a copy of every per-message `.proto`, `_service.proto` and the
      framework protos (`errorCode`, `heartBeat`, `capabilities_service`)
      under `<dest>/python/proto/`.
    - `_pb2.py`, `_pb2.pyi` and `_pb2_grpc.py` compiled from them at
      **generation time**.
  - protoc / grpc_tools absent → a non-fatal logged `Error`, same as
    `ProtoFile/ProtoCompiler.py`.
- **Decision needed (bring to Rafael before implementing):** the import
  path of the generated `_pb2` modules. protoc derives Python imports from
  `.proto` import paths, so `import "protofiles/x.proto"` becomes
  `from protofiles import x_pb2`, a generic top-level name. Options:
  - (a) ship a top-level `protofiles` package (simple; the name may collide
    in a consumer's environment);
  - (b) copy the protos under `harpia_generated/protofiles/` and rewrite
    their import lines, giving `from harpia_generated.protofiles import
    x_pb2`. The descriptor-pool file names then differ from C++/Java's;
    wire bytes are unaffected.
  - (c) protoc as in (a), then post-process the generated imports.

  Recommendation: (b), with a test that the wire bytes match the C++
  encoding of the same message.
- **Out of scope:** any runtime beyond empty packages (later epics); docs
  and lint config (task 3).
- **Tests:**
  - `UnitTests/test_golden_python.py` + `UnitTests/golden_python/`:
    whole-`python/`-tree snapshot, mirroring `test_golden_java.py`
    (`HARPIA_UPDATE_GOLDEN=1`; regenerating twice leaves mtimes untouched).
  - A protoc-gated test that imports every generated `_pb2` module,
    round-trips one message through `SerializeToString`/`ParseFromString`,
    and checks the bytes equal the C++ target's encoding of the same
    message (built the way `test_stage7` builds a probe).
  - `golden/` and `golden_java/` unchanged.
  - A stale `<name>_<hash>_pb2.py` from a renamed message is pruned by
    `prune_stale_outputs`.
