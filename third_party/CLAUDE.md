# third_party — vendored C++ libraries for the generated build

**Role:** Vendored (checked-in) third-party C++ dependencies that the harpia-generated CMake project links against. They are consumed by the generated code / build, not by the Python generator itself.

## Contents
- `sqlite/` — SQLite, embedded database used by generated ORM/persistence code.
- `tinyxml2/` — TinyXML-2, XML parsing/serialization (SOAP/XML adapters).
- `crow/` — Crow, header-only C++ HTTP server framework (`crow.h`, the upstream
  amalgamated `crow_all.h`). Backs the generated REST (Stage 12) and SOAP (Stage 11)
  servers. Replaced the former cpp-httplib dependency.
- `asio/` — standalone asio (no Boost, no OpenSSL), the transport library Crow
  requires. Header-only tree (`asio.hpp` + `asio/`). Vendored so generated output
  stays self-contained and cross-compilable across target boards without a system
  `libasio-dev`.
- `cyclonedds/` + `cyclonedds-cxx/` — Eclipse Cyclone DDS (C core) and its
  `ddscxx` ISO-C++ binding, the DDS transport for the **dds-transport** epic
  (ASTM F2761 / OpenICE-class bedside bus). **Different from the entries above:**
  a full CMake C library, no amalgamation, not apt-available on Ubuntu 24.04.
  **Hybrid vendoring** — the source snapshot is checked in here for provenance /
  SBOM, but it is *built once in the Docker toolchain image* (`Docker/Dockerfile`
  `COPY`s these trees and `cmake --install`s them to `/usr/local`), the same
  "heavier lib, built in the image, like on a board" posture as
  protobuf/gRPC/ZMQ/SOCI — **not** `add_subdirectory`'d into every generated
  project. See each dir's `VENDORED.md`. `UnitTests/dds_spike/` +
  `UnitTests/test_dds_vendor_spike.py` build a tiny pub/sub against the image's
  install to prove the stack.

## Key facts / gotchas
- **Do not edit** the library sources — they are upstream vendored copies. Update by re-vendoring the upstream release, not by patching in place. **One sanctioned exception:** `crow/crow.h` carries deliberate local edits, each tagged `[harpia patch]` and documented in `crow/VENDORED.md` "Local patches" (the transport-authn RBAC task needs the client-cert CN, which upstream Crow never exposes to a handler). `grep -n "\[harpia patch\]" crow/crow.h`; re-apply on any re-vendor.
- These are inputs to the *generated* C++ build (the CMake tree under `HARPIA_OUTPUT_DIR`, e.g. `HarpiaTest/test_build`), not imported by any Python module.
- The pipeline copies its own scaffolding from `Assets/` (proto, server/client templates, CMake); these libraries are the compile-time deps that scaffolding and generated adapters rely on.
