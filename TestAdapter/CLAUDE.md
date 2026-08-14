# TestAdapter — Stage 14: emits C++ unit + app-level tests for the generated code

**Pipeline role / purpose:** Stage 14. Last adapter run in the pipeline. For each
table-bearing message it generates a self-contained C++ test program that
exercises every earlier stage's output (message accessors, CRUDL DB, JSON, XML,
REST, SOAP, access rights/modifiers), plus one whole-application test. It also
writes the generated project's `tests/CMakeLists.txt` (one CTest per message) and
vendors third-party deps into the generated tree so it stays self-contained.

**Entry points:** `TestAdapter(messages=<Message list>, dest=<build dir>).Process()`.
Invoked from `main.py` and `tests/run_pipeline.py` after all other adapters.

**Inputs → Outputs:**
- In: `messages` (Message objects) + `dest` build dir.
- Out (under `dest/tests/`): `<name>_<md5Hash>_test.cpp` per table message,
  one `app_<md5Hash>_test.cpp`, and `CMakeLists.txt`. Also copies vendored deps
  into `dest/third_party/` (`sqlite`, `tinyxml2`, `crow`, and the `asio` header
  tree) and the HTTP test client `harpia_test_client.h` next to the tests (Crow
  ships no client).
- Tests are opt-in: only built when top-level CMake gets `-DHARPIA_BUILD_TESTS=ON`.

## Files
- `TestAdapter.py` — the whole adapter. Class `TestAdapter`; `Process()` loops
  `_tables()` (non-enum messages with a `tableName`), renders each via `_render`
  (fills `test.cpp.tmpl`), picks a representative message (`_pick_rep`) for the
  app test rendered via `_app_render` (fills `app.cpp.tmpl`), vendors deps
  (`_vendor_deps`), and writes CTest wiring (`_write_cmake`).
- `templates/test.cpp.tmpl` — per-message test skeleton. `str.format` placeholders
  (`{cls}`, `{crudl_header}`, `{simple_body}`, `{db_body}`, `{ar_body}`,
  `{am_body}`, `{json_body}`, `{xml_body}`, `{rest_body}`, `{soap_body}`). Real
  C++ braces are escaped `{{ }}`. `main()` runs each check; each returns a
  distinct nonzero code so a CTest failure pinpoints the assertion.
- `templates/app.cpp.tmpl` — app-level test skeleton (`{all_good}`, `{crash}`,
  `{slower}`, `{non_parseable}`), covering 14.11–14.14.

## Key facts / gotchas
- Body builders return C++ source as strings; `_value`/`_map_key`/`_map_val`
  produce deterministic literals (variant "a"/"b" distinguish the two CRUDL rows).
- Uses `Database.model.analyze/type_registry/map_fields/repeated_fields` to derive
  columns (bindable / pk / embed / map / repeated). Repeated-FK (1-to-many) scalars
  are skipped in the generated `_db_body` — they're covered by the host test instead.
- Headers are referenced by `<name>_<md5Hash>_<kind>.h`, so the md5Hash must match
  what the other adapters emit (all keyed off `Message.md5Hash`).
- `_pick_rep` prefers a message with a PK + text field + no composed field so the
  cross-layer app round-trip stays flat/deterministic.
- Credential gates: SOAP uses `<credentials><user>=msg.name</user><pswd>=md5Hash`;
  REST uses `X-User`/`X-Pswd` headers. Wrong/absent → 401.
- `_vendor_deps` copies from repo `third_party/` only if present; `_write_cmake`
  compiles sqlite as C (`enable_language(C)`), links `protofiles harpia_sqlite
  harpia_tinyxml2`, adds `add_test` per unit.
- `_write_cmake`'s emitted CMake carries the same Windows `if(WIN32)` SOCI/vcpkg
  branch as `examples/consumer` (see `Assets/CLAUDE.md`), plus its own
  `HARPIA_TEST_PROTO_INCLUDE_DIR` variable (same protobuf-version-skew fix as
  server/client/consumer — lists the vcpkg-regenerated `${CMAKE_BINARY_DIR}/proto`
  ahead of the Docker-baked `generated/cpp` on the include path) and a
  `ws2_32` link per test target. `tests/harpia_test_client.h`, the REST/SOAP
  HTTP round-trip test client it vendors, is Winsock2-ported alongside its
  POSIX path (`#ifdef _WIN32`). Verified end to end on Windows (`USAGE.md`
  §11): `10/10` ctest targets pass on native MSVC + vcpkg, including
  `app_test` which drives a real Crow REST/SOAP round trip through the
  ported client.

## Touchpoints
- Called by: `main.py`, `tests/run_pipeline.py`.
- Depends on: `Util.util.loadTemplate` (reads templates dir next to this file),
  `Database.model`, `Logger.logger`, repo-level `third_party/`.
- Verified by: `tests/test_stage14.py` and golden snapshots in
  `tests/golden/gen_tests/`.
