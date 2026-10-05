# PyTests — the Python target's generated test suite

**Pipeline role / purpose:** python-target / py-tests. The Python side of
`TestAdapter/` (C++ `tests/<name>_<hash>_test.cpp`). A stage of
`LangBackend/python.py`'s `run_python`, after `PyDdsAdapter`.

**Entry point:** `PyTestAdapter(messages, dest, compliance).Process()` →
`None` (nothing without a table-bearing message).

## Runtime (`runtime/testing.py` → `harpia_runtime.testing`)
`sample(cls, variant="a", pk=1, id_base=1000)` — every field filled with the
C++ `TestAdapter._value` rules (text `"<field>_<variant>"`, enum 1 (first
value if 1 isn't one), floating 2.5/3.5, 64-bit 7/8, else 1/True); composed
fields recursively (embed, FK, repeated children), repeated + maps 2 entries
(`_map_key`/`_map_val` rules), nested `ID_` distinct from `id_base` (FK
children become distinct rows). `check_field_access(cls)`;
`create_tables(conn, dao_cls)` (the DAO's table + the tables reachable by FK
— **not** every table: `users` / `top_users` share `user_table` with
different columns, the registry note); `persisted_view(dao_cls, msg)`
(columns, FK children's views, map/repeated/composed child tables).
Task 2: `serve(pool, rest=, soap=, rest_base="/api/v1", soap_base="/soap")`,
`request(port, method, path, body, headers, timeout)`, `soap_envelope`,
`probe_text(cls)`, `fake_request(headers)`.

## Generated (`<dest>/python/tests/`)
- `test_<name>_<hash>.py` per table-bearing message: `test_field_access`,
  `test_json_round_trip`, `test_xml_round_trip`, `test_yaml_round_trip`,
  `test_to_string` (round trip for every `Format`, or — when
  `tree_has_phi` — the `[REDACTED]` placeholder, by design), and
  `test_crudl_round_trip` (temp-file SQLite, direct connection: create 2 /
  read / missing read / list / page / update with variant b / remove).
  **Task 2** adds, per message and flat-or-RBAC exactly as
  `Database.auth_gate.effective_rbac` (imported): `test_access_modifiers`
  (duplicate PK → `sqlite3.IntegrityError`), `test_access_rights` (flat: the
  generated `EARLY_GATE` / `GATE` on good / wrong / no credential; RBAC: the
  `permitted()` spread + `decide("", create) is unauthenticated`),
  `test_rest_api` / `test_soap_api` (flat: full credentialed round trips
  incl. XML negotiation, compared with `persisted_view`; RBAC: an anonymous
  caller is 401 / 401 Fault everywhere — an mTLS identity is the harness's
  job, as in C++). Served by `testing.serve` on a plain in-process router
  (the per-message `register()`s), like the C++ tests' Crow app — not the
  generated mTLS `HttpServer`.
- `test_app_<hash>.py` (task 2) on `TestAdapter._pick_rep`'s message (the
  C++ rule, called): `test_slower` (150 ms handler + a dead port bounded),
  `test_non_parseable` (JSON / XML parse failures, SOAP 400, REST 400 flat /
  401 RBAC), `test_crash` (no tables → `sqlite3.Error`, REST 500 flat / 401
  RBAC), `test_all_good` (flat REST POST → SOAP get → DAO read; RBAC DAO +
  serializers + fail-closed HTTP).
- `conftest.py` puts the project root on `sys.path`.
- `pyproject.toml` (PyAdapter template): `test = ["pytest>=7"]` extra,
  `[tool.pytest.ini_options] testpaths = ["tests"]`, and `tests/**` shares
  the generated-code E501 exemption (hash-qualified names).

Run from `<dest>/python`: `pip install .[test] && pytest`.

## Touchpoints
- Depends on: the DAOs (`PyDatabase`), the serialization runtimes.
- Tested by: `UnitTests/test_python_generated_tests.py` (runs the emitted
  suite), the golden (`UnitTests/golden_python/tests/`).
