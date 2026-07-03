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
  into `dest/third_party/` (`sqlite`, `tinyxml2`, `cpp-httplib`).
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

## Touchpoints
- Called by: `main.py`, `tests/run_pipeline.py`.
- Depends on: `Util.util.loadTemplate` (reads templates dir next to this file),
  `Database.model`, `Logger.logger`, repo-level `third_party/`.
- Verified by: `tests/test_stage14.py` and golden snapshots in
  `tests/golden/gen_tests/`.
