# Assets — CMake / proto / C++ templates copied into the generated build

**Role:** Static scaffolding (not generated) that the pipeline copies into the output build tree to make it compilable. Consumed by `Util/util.py` copy helpers, invoked from `main.py` (and `tests/run_pipeline.py`) after code generation.

## Contents
- `CMakeLists.txt` — root of the generated project. `add_subdirectory(client|server|proto)`, C++17. Opt-in `tests/` via `-DHARPIA_BUILD_TESTS=ON` (Stage 14 generated unit tests).
- `vcpkg.json` — Windows-only manifest (`protobuf`, `grpc`, `zeromq`, `cppzmq`, `soci[sqlite3]`), copied to `<dest>/vcpkg.json` by `copyCMakeFiles` alongside the root CMakeLists so vcpkg's toolchain-file manifest mode auto-detects it. Unused on the apt-based Linux/Docker path.
- `proto/CMakeLists.txt` — builds the `protofiles` library; globs `protofiles/*.proto`, runs `protobuf_generate` for cpp + grpc. Tries Protobuf CONFIG then falls back to MODULE (Debian/Ubuntu apt).
- `proto/protofiles/errorCode.proto`, `heartBeat.proto` — framework standard messages, copied verbatim by `copyBasicProtos`.
- `proto/protofiles/Service.proto` — NOT copied verbatim; it is a template with `%USER_MESSAGE%` / `%USER_MESSAGE_FILE_NAME%` placeholders, read via `util.readFromTemplate` / filled by `ProtoFile/FileCreator.py`. Defines the gRPC service (heartBeat, streamSrc, pullByID, push).
- `server_template/` and `client_template/` — each has `CMakeLists.txt` + `src/main.cpp`. End-to-end ZMQ demo (server=PULL, client=PUSH) that exercises the generated json/ and zmq/ adapters.

## Key facts / gotchas
- Copy flow (see `Util/util.py`), dest = `HARPIA_OUTPUT_DIR` (default `./HarpiaTest/test_build`):
  - `copyBasicProtos` -> `<dest>/proto/protofiles/{errorCode,heartBeat}.proto`
  - `copyCMakeFiles` -> root `CMakeLists.txt`, `<dest>/proto/`, `<dest>/server/`, `<dest>/client/` CMakeLists
  - `copyServerClientTemplates` -> `<dest>/{server,client}/src/main.cpp` via `_emitTemplate`
- `main.cpp` placeholders `%DEMO_MESSAGE%`, `%DEMO_HASH%`, `%DEMO_SAMPLE_JSON%` are substituted by `_emitTemplate` from the demo dict (`chooseDemo` picks first push/pull message). If there is no push/pull message, `_emitTemplate` writes a trivial compiling stub instead.
- Server/client CMake include `${CMAKE_SOURCE_DIR}/generated/cpp` (harpia-generated json/zmq adapters) and link `protofiles` + `zmq` on Linux.
- **Windows (verified, see `USAGE.md` §11):** server/client CMakeLists branch on `if(WIN32)` — link `cppzmq` (vcpkg CONFIG target) instead of bare `zmq`, and list `${CMAKE_BINARY_DIR}/proto` *ahead of* `generated/cpp` on the include path so the adapter headers' `#include "protofiles/...pb.h"` resolves to `proto/CMakeLists.txt`'s freshly vcpkg-protoc-regenerated copy instead of the Docker-baked one (a protobuf version mismatch otherwise fails to compile — Google has removed/moved internal headers like `map_field_inl.h` across major versions). The Linux branch is untouched.
- These are hand-maintained source templates — edit here to change generated-project scaffolding; do not edit copies under `test_build/` (regenerated/gitignored).
