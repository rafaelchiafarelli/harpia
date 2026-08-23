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