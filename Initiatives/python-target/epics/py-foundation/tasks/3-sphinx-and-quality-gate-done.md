## Sphinx skeleton + `mypy --strict` + `ruff` gate for the generated tree

- **Depends on:** task 2.
- **Contract:**
  - `<dest>/python/docs/` holds `conf.py` (autodoc + napoleon, Google-style
    docstrings) and `index.rst`. `sphinx-build -W` (warnings are errors)
    builds HTML from the docstrings of `harpia_runtime` and
    `harpia_generated`. This is the Python counterpart of the
    `Doxygen/mainpage.py` F6 plumbing. The landing page pulls the same
    USAGE.md sections the Doxygen mainpage does, if that is cheap.
    Otherwise it links to them; say which.
  - `pyproject.toml` `[tool.mypy]`: `strict = true`; `_pb2.py` is typed
    through its `.pyi` stub. `_pb2_grpc.py` is excluded or given
    `ignore_errors` because grpc_tools emits untyped code. Record which,
    with the reason.
  - `[tool.ruff]`: a rule set (at least `E,F,W,I,B,UP`) with generated
    protoc output excluded.
  - Templates and runtimes from every later epic must pass this gate.
    That is part of each epic's DoD.
- **Out of scope:** writing docstrings for runtimes that don't exist yet
  (each epic adds its own, Ground Rule 6).
- **Tests:** `UnitTests/test_python_quality_gate.py` (image-gated). It
  generates the fixture project and asserts `mypy --strict`, `ruff check`
  and `sphinx-build -W` all exit 0. A deliberately bad template line
  injected in a temp copy makes the gate fail (a negative control, so a
  silently-skipped gate can't pass).
