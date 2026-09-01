## Fuzz harness — XML parser

Scoped 2026-09-01. Task 3 of static-fuzz-ci. A thin addition on task 2's
shared driver: the XML-parser target + its seed corpus.

### Decisions (settled during scoping — do not re-litigate)

- **XML target:** `harpia::xml::from_xml(const std::string&, Message*)`
  (`XmlAdapter/runtime/harpia_xml.h:205`). Same scratch-message approach
  as task 2's JSON target.
- Fills in task 2's `-DHARPIA_FUZZ_TARGET=xml` branch — no new driver, no
  new pytest module, one more parametrized case in
  `UnitTests/test_fuzz_parsers.py`.
- **Seed corpus:** `UnitTests/fuzz/corpus/xml/` — valid nested element,
  empty doc, unbalanced tags, deep nesting, entity/`CDATA` edge cases,
  XML-bomb-shaped (bounded) input, declaration-only.

### Contract

**In:** `harpia_xml.h` (repo, present); task 2's driver.

**Required:** **task 2 merged** (the driver + the pytest shell). Nothing
else.

**Delivered:**
- `UnitTests/fuzz/harpia_fuzz_main.cpp` — the `xml` target implemented
  (the `#error` stub from task 2 replaced).
- `UnitTests/fuzz/corpus/xml/*` — the seed corpus.
- `UnitTests/test_fuzz_parsers.py` — the XML case activated in the
  parametrized job.

**Pre-work:** the seed corpus files (hand-written, this task).

**Tests:** the fuzz run *is* the test. Acceptance gate: default
`HARPIA_FUZZ_ITERS`, clean exit in Docker, before marking done.

**Out of scope:** the SOAP target (task 4); anything task 2 already ruled
out.

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Depends only on task 2.
