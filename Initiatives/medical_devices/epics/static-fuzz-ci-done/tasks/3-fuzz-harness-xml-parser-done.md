## Fuzz harness — XML parser

Scoped 2026-09-01. **Implemented 2026-09-01.** Task 3 of static-fuzz-ci. A
thin addition on task 2's shared driver: the XML-parser target + its seed
corpus.

### Decisions (as implemented)

- **XML target:** `harpia::xml::from_xml(const std::string&, Message*)`
  (`XmlAdapter/runtime/harpia_xml.h`) — tinyxml2 parse + a reflection walk
  (`detail::read_message`). Same in-process scratch `FuzzMsg` descriptor as
  task 2's JSON target.
- Filled task 2's `-DHARPIA_FUZZ_TARGET=xml` branch: one `#include
  "xml/harpia_xml.h"` and one `return ::harpia::xml::from_xml(...)` line in
  `harpia_fuzz_main.cpp` (the `#error` stub replaced). **No new driver, no
  new pytest module** — `TARGETS` in `UnitTests/test_fuzz_parsers.py` grows
  from `["json"]` to `["json", "xml"]` and the existing parametrized job
  covers it.
- **Seed corpus:** `UnitTests/fuzz/corpus/xml/` — 10 checked-in files:
  valid nested element, empty doc, declaration-only, unbalanced tags, deep
  nesting, entity + `CDATA` edge cases, a bounded XML-bomb-shaped
  (`<!ENTITY>` expansion) input, attributes + namespace prefixes,
  wrong-scalar text per field type, many-repeated + long `bytes`.

### Contract

**In:** `harpia_xml.h` (repo); task 2's driver + pytest shell.

**Required:** **task 2 merged** — met (task 2 is in `tasks` at `2a34217`).

**Delivered:**
- `UnitTests/fuzz/harpia_fuzz_main.cpp` — the `xml` target implemented.
- `UnitTests/fuzz/corpus/xml/*` — the 10-file seed corpus.
- `UnitTests/test_fuzz_parsers.py` — `xml` active in `TARGETS`.

**Pre-work:** the seed corpus files, hand-authored by this task.

**Tests:** the fuzz run *is* the test. Acceptance gate — met: default
`HARPIA_FUZZ_ITERS`, clean exit in Docker
(`test_fuzz_parsers.py` — `2 passed in ~5s`, `json` + `xml`). One-off
longer campaign: **2×2 000 000 mutations** (seeds `0x9E3779B9` and
`0xBADF00D`), ~15–18 s each, no sanitizer trip.

**Out of scope:** the SOAP target (task 4); anything task 2 already ruled
out (persistent corpus, coverage-guided mutation, a nightly job).

### Implementation notes

- `harpia_xml.h`'s `read_message` only recurses into a child element when
  it names a *message-typed* field of the current descriptor, so the
  `deep_nesting.xml` seed exercises tinyxml2's own parse-depth handling
  (`XML_MAX_DEPTH`), not unbounded reflection recursion — `FuzzInner` has
  no sub-message field. Bounded by construction.
- Per the per-task test-scope rule, only `test_fuzz_parsers.py` was run for
  this task; the full suite runs at the `tasks → static-fuzz-ci → epics`
  merge-up.

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Depends only on task 2.
