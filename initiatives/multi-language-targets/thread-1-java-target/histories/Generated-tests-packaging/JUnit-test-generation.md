### Session J.21 — JUnit test generation

- **Depends on:** J.6 (or further DB work), J.4, J.10/J.11 merged — needs
  real emitters to generate meaningful tests against.
- **Deliverable:** JUnit 5 test generation — a Java-source-emitting
  counterpart for each of `TestAdapter.py`'s ~8 body builders
  (`_db_body`/`_json_body`/`_ar_body`/`_am_body`/`_xml_body`/`_rest_body`/
  `_soap_body`/`_simple_body`), mechanical per-builder since they already
  consume `Database.model`'s language-agnostic IR directly — genuinely
  one deliverable despite the ~8 sub-parts, since each is a stamp of the
  same pattern, not independent design work.
- **Tests:** the generated JUnit tests running successfully via Gradle's
  `test` task, once J.22 exists, is this session's own acceptance check
  (verified together with J.23, not duplicated here).

## Implementation notes (landed 2026-08-23)

Scoped to 4 of the ~8 C++ body builders: field access (14.1), JSON round
trip (14.5), XML round trip (14.6), DB CRUDL round trip (14.2) — all
built via `Descriptor`/`FieldDescriptor` reflection rather than the
generated typed builder API, since a wrong hand-derived camelCase
accessor name here would be a **compile failure** in generated code, not
just a latent runtime bug. `_access_rights_body`/`_access_modifiers_body`
(nothing to test — no access-modifier implementation exists for the Java
target), `_rest_body`/`_soap_body` (already covered directly by this
repo's own `tests/test_java_rest.py`/`test_java_soap.py`), and the
app-level all-good/crash/slower/non-parseable suite are NOT ported —
flagged, not silently assumed covered. Full rationale in
`JavaTestAdapter/CLAUDE.md`.

`test { useJUnitPlatform() }` + the `junit-jupiter` `testImplementation`
dependency were added to `project.gradle.tmpl` as part of this session
(enabling JUnit 5 is this deliverable's own concern).

This session's own acceptance bar — the generated tests actually running
green via `gradle test` — is verified by `tests/test_java_junit_tests.py`,
landing now (not deferred to J.23) since both prerequisites (JUnit wiring,
real DAOs/JSON/XML runtimes) already existed.