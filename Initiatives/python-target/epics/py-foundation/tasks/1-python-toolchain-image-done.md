## Python toolchain in the `harpia-build` image

- **Depends on:** nothing (can run in parallel with `lang-backend-seam`).
- **Contract:** the Docker image can generate, type-check, lint, document
  and run a Python-target project with no network access at test time.
  - **apt** (matches the image's `protoc` 3.21.12, decided 2026-10-03):
    `python3-protobuf`, `python3-grpcio`, `python3-grpc-tools`,
    `python3-zmq`, `python3-psycopg`, `python3-mypy`, `python3-sphinx`.
  - **pinned pip** (not in noble's apt): `ruff`, `mypy-protobuf`
    (`protoc-gen-mypy`, for `.pyi` stubs `mypy --strict` needs), and
    `cyclonedds==0.10.5` built against the vendored Cyclone already
    installed to `/usr/local` (`CYCLONEDDS_HOME=/usr/local`). It must be the
    same 0.10.5 so the Python and C++ DDS stacks match.
  - Every pin and its reason recorded in the Dockerfile's header comment
    block, same style as the existing entries.
- **Pre-work:** confirm each apt package exists in noble at a version
  compatible with protoc 3.21 gencode. **Decision needed** if one doesn't:
  pin it via pip instead and say so. Never silently mix runtimes that can't
  load the generated code.
- **Watch for:** `grpc_tools.protoc` bundles its own protoc. Use the
  system `protoc` for `--python_out`/`--pyi_out` and `grpc_tools` only for
  `--grpc_python_out`, so message gencode matches the C++ side's protoc.
  Check `zmq.has("curve")` is true (Ubuntu's libzmq links libsodium).
- **Out of scope:** any generator change (task 2).
- **Tests:** `UnitTests/test_python_toolchain.py`, skipped outside the
  image. It asserts:
  - each module imports and reports the pinned/expected version;
  - `zmq.has("curve")`;
  - `cyclonedds.__version__ == "0.10.5"`;
  - `ruff`, `mypy` and `sphinx-build` run;
  - a trivial `.proto` compiles with `protoc --python_out --pyi_out` +
    `grpc_tools` and the result imports.
