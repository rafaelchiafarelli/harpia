# third_party — vendored C++ libraries for the generated build

**Role:** Vendored (checked-in) third-party C++ dependencies that the harpia-generated CMake project links against. They are consumed by the generated code / build, not by the Python generator itself.

## Contents
- `sqlite/` — SQLite, embedded database used by generated ORM/persistence code.
- `tinyxml2/` — TinyXML-2, XML parsing/serialization (SOAP/XML adapters).
- `cpp-httplib/` — cpp-httplib, header-only HTTP client/server (RESTful adapters).

## Key facts / gotchas
- **Do not edit** the library sources — they are upstream vendored copies. Update by re-vendoring the upstream release, not by patching in place.
- These are inputs to the *generated* C++ build (the CMake tree under `HARPIA_OUTPUT_DIR`, e.g. `HarpiaTest/test_build`), not imported by any Python module.
- The pipeline copies its own scaffolding from `Assets/` (proto, server/client templates, CMake); these libraries are the compile-time deps that scaffolding and generated adapters rely on.
