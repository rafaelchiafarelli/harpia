# LangBackend — the generation-target registry

**Pipeline role / purpose:** Picks which language target(s) `main.py`
generates. Same shape as `Database/backends` (the DB-dialect registry):
`get_lang_backend(name)` resolves an explicit name or alias, empty/unset
means the default (`cpp`), and an unknown name raises `ValueError`.

**Entry point:** `get_lang_backend(os.environ.get("HARPIA_GEN_LANG"))`
returns a stateless singleton `LangBackend`; `backend.run(ctx)` runs every
generation stage of that target. `ctx` is a frozen `GenerationContext`
(`messages`, `dest`, `compliance`, `db_backend`, `crypto_backend`,
`root_hash`, `log`) built once by the front end. `ctx.report(err)` logs a
stage's non-fatal `Error`.

## Backends
- `cpp.py` — `CppBackend`, the default. `main.py`'s former unconditional
  stage list, moved verbatim: demo templates + CMake, Doxygen, protoc, JSON,
  gRPC, ZMQ, events, capability handshakes, DDS, XML/YAML/serialize, SQL,
  CRUDL, registry, migrations, dbio, REST/SOAP/WSDL/SDC, generated tests,
  SBOM.
- `java.py` — `JavaBackend(CppBackend)`: `run_java()` (the former inline
  `if genLang == "java":` block, verbatim: Gradle, JSON, JDBC runtime +
  DAOs, XML, REST, SOAP, ZMQ, JUnit) then the unchanged C++ pipeline. Java
  is additive on top of C++, as it always was.
- `python.py` — `PythonBackend(CppBackend)`: `run_python()` (the Python
  target's stages: `PyAdapter`, `PySerializationAdapter`,
  `PyDatabaseAdapter`, `PyEventsAdapter`, `PyZmqAdapter`, `PyHttpAdapter`, `PyGrpcAdapter`, ..., `PyDocsAdapter` last) then
  the C++ pipeline — the same additive rule as `java`. Alias `py`.

## Key facts / gotchas
- **An unknown `HARPIA_GEN_LANG` is a hard error** (decided at
  lang-backend-seam task 3, 2026-10-04). Before the seam, any unrecognized
  value silently fell through to the C++-only path. `main.py` now resolves
  the backend before it creates the output dir, so a typo exits non-zero
  and writes nothing. Unset or empty still means `cpp`.
- Verified at the switch: `cpp` and `java` output trees are byte-identical
  to the pre-seam `main.py` (1343 / 1482 files), apart from the SBOM's git
  metadata fields.
- `db_backend` and `crypto_backend` are resolved **once** in `main.py`
  and carried on the context. A backend never re-resolves them, so every
  target in one run shares the identical object (`JavaDatabase/CLAUDE.md`).
- `GradleAdapter` must run after the front end's `copyBasicProtos` (it
  copies `errorCode`/`heartBeat.proto`). The front end stays in `main.py`
  and always runs before any backend, so this holds by construction.
- Adding a language means one new module plus one entry in `_REGISTRY`
  (`__init__.py`). No existing backend class changes.

## Touchpoints
- Depends on: every C++ generation adapter (imported by `cpp.py`).
- Called by: `main.py`.
- Tested by: `UnitTests/test_lang_backend.py`.
