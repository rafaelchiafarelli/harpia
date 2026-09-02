## Fuzz harness — SOAP parser

Scoped 2026-09-01. **Implemented 2026-09-01.** Task 4b of static-fuzz-ci,
and the epic's last task. A thin addition on task 2's driver: the
SOAP-parser target + seed corpus.

Was task 4; split into **4a** (extract the SOAP parse seam — it had no
standalone string→message entry point) + this **4b** (fuzz the extracted
seam), approved 2026-09-01.

### Decisions (as implemented)

- **SOAP target:** `harpia::soap::message_from_request(const std::string&,
  ::google::protobuf::Message*)` from `SoapAdapter/runtime/harpia_soap.h`
  (task 4a) — `parse_envelope` → `find_operation` (Envelope → Body →
  operation element) → `harpia::xml::from_xml_element` on the operation's
  first child. No socket, no DB, no auth. Same in-process scratch `FuzzMsg`
  descriptor as tasks 2/3.
- Filled task 2's `-DHARPIA_FUZZ_TARGET=soap` branch in
  `harpia_fuzz_main.cpp`: one `#include "soap/harpia_soap.h"` + one
  `return ::harpia::soap::message_from_request(...)` line. `TARGETS` in
  `UnitTests/test_fuzz_parsers.py` → `["json", "xml", "soap"]`. No new
  driver / pytest module.
- **Seed corpus:** `UnitTests/fuzz/corpus/soap/` — 12 checked-in files:
  valid `set` (with header + nested/repeated payload), valid `get` and
  `delete` (id-only), bodyless envelope, empty body, missing `Envelope`,
  wrong namespace, nested Fault burying a `set`, oversized header,
  operation element with no payload, non-XML garbage, deep `<set>` nesting.

### Contract

**In:** `SoapAdapter/runtime/harpia_soap.h` (task 4a); task 2's driver +
pytest shell.

**Required:** **task 4a merged** — met (in `tasks` at `598cd2f`).
Independent of task 3.

**Delivered:**
- `UnitTests/fuzz/harpia_fuzz_main.cpp` — the `soap` target implemented
  (the `#error` stub from task 2 replaced).
- `UnitTests/fuzz/corpus/soap/*` — the 12-file seed corpus.
- `UnitTests/test_fuzz_parsers.py` — `soap` active in `TARGETS`.

**Pre-work:** the seed corpus files, hand-authored by this task.

**Tests:** the fuzz run *is* the test. Acceptance gate — met: default
`HARPIA_FUZZ_ITERS`, clean exit in Docker (`test_fuzz_parsers.py` —
`3 passed in ~7s`, json + xml + soap). One-off longer campaign:
**2×2 000 000 SOAP mutations** (seeds `0x9E3779B9` and `0x5EED`), ~12–16 s
each, no sanitizer trip. Epic close-out: full suite, then
`tasks → static-fuzz-ci → epics`.

**Out of scope:** WS-Security / MTOM parsing; the WS-Discovery responder
(sdc-biceps); a nightly job.

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Depends on task 4a (and, transitively, task 2).
Closes the epic.
