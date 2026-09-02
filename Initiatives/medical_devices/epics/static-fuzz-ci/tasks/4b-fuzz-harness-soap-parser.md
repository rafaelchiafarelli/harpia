## Fuzz harness — SOAP parser

Scoped 2026-09-01. Task 4b of static-fuzz-ci, and the epic's last task. A
thin addition on task 2's driver: the SOAP-parser target + seed corpus.

Was task 4; split into **4a** (extract the SOAP parse seam — the parse
path had no standalone entry point, it was welded into the crow handler)
and this **4b** (the fuzz target on the extracted seam), approved
2026-09-01.

### Decisions (settled during scoping — do not re-litigate)

- **SOAP target:** `harpia::soap::message_from_request(const std::string&,
  ::google::protobuf::Message*)` from `SoapAdapter/runtime/harpia_soap.h`
  (delivered by task 4a) — Parse → Envelope → Body → operation element →
  first-child payload → `harpia::xml::from_xml_element`. No socket, no DB,
  no auth. Same in-process scratch `FuzzMsg` descriptor as tasks 2/3.
- Fills task 2's `-DHARPIA_FUZZ_TARGET=soap` branch in
  `harpia_fuzz_main.cpp`; `TARGETS` in `UnitTests/test_fuzz_parsers.py`
  grows to `["json", "xml", "soap"]`. No new driver / pytest module.
- **Seed corpus:** `UnitTests/fuzz/corpus/soap/` — a valid `set` envelope,
  a bodyless envelope, wrong-namespace, missing-`Envelope`, nested-fault,
  oversized-header, a `get`/`delete` (id-only) envelope, non-XML garbage.

### Contract

**In:** `SoapAdapter/runtime/harpia_soap.h` (task 4a); task 2's driver +
pytest shell.

**Required:** **task 4a merged.** Independent of task 3.

**Delivered:**
- `UnitTests/fuzz/harpia_fuzz_main.cpp` — the `soap` target implemented
  (the `#error` stub from task 2 replaced).
- `UnitTests/fuzz/corpus/soap/*` — the seed corpus.
- `UnitTests/test_fuzz_parsers.py` — `soap` active in `TARGETS`.

**Pre-work:** seed corpus files (this task). The parse entry point is
delivered by task 4a — not pre-work here.

**Tests:** the fuzz run *is* the test. Acceptance gate: default
`HARPIA_FUZZ_ITERS`, clean exit in Docker
(`test_fuzz_parsers.py`), before marking done. This is also the epic's
close-out — after this merges, run the full suite, then
`tasks → static-fuzz-ci → epics`.

**Out of scope:** WS-Security / MTOM parsing; the WS-Discovery responder
(that is sdc-biceps); a nightly job.

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Depends on task 4a (and, transitively, task 2).
Closes the epic.
