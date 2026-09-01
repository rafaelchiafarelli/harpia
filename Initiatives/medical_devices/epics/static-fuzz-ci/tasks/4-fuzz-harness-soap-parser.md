## Fuzz harness — SOAP parser

Scoped 2026-09-01. Task 4 of static-fuzz-ci, and the epic's last task. A
thin addition on task 2's driver: the SOAP-parser target + seed corpus.

### Decisions (settled during scoping — do not re-litigate)

- **SOAP target:** the envelope/body parse path in the Stage 11 SOAP
  runtime — the request-parsing helper that turns a SOAP envelope string
  into a message, **without** binding a socket. Locate the exact entry
  point in the generated `soap/` headers / the SOAP runtime during
  implementation (`Database/SoapAdapter.py` / `WsdlAdapter.py` output);
  if the only parse path is welded to the HTTP handler, extract the pure
  string→message step as a small internal helper rather than fuzzing
  through a socket — flag that as the one shape question this task may
  surface.
- Fills task 2's `-DHARPIA_FUZZ_TARGET=soap` branch; one more parametrized
  case in `UnitTests/test_fuzz_parsers.py`. No new driver/module.
- **Seed corpus:** `UnitTests/fuzz/corpus/soap/` — a valid envelope, a
  bodyless envelope, wrong-namespace, missing-`Envelope`, nested-fault,
  oversized-header, non-XML-garbage.

### Contract

**In:** the Stage 11 SOAP parse entry point (repo, present); task 2's
driver.

**Required:** **task 2 merged.** Independent of task 3.

**Delivered:**
- `UnitTests/fuzz/harpia_fuzz_main.cpp` — the `soap` target implemented.
- `UnitTests/fuzz/corpus/soap/*` — the seed corpus.
- `UnitTests/test_fuzz_parsers.py` — the SOAP case activated.
- If a pure parse helper had to be extracted from the HTTP handler: a
  one-line note in `Database/SoapAdapter.py`'s `CLAUDE.md` (or the
  relevant runtime header) recording the seam.

**Pre-work:** seed corpus files (this task). Identifying the parse entry
point is implementation, not pre-work — but if it turns out to need a
non-trivial refactor of the SOAP runtime, stop and flag it as its own
task rather than absorbing it here.

**Tests:** the fuzz run *is* the test. Acceptance gate: default
`HARPIA_FUZZ_ITERS`, clean exit in Docker, before marking done. This is
also the epic's close-out — after this merges, `tasks → static-fuzz-ci →
epics`.

**Out of scope:** WS-Security / MTOM parsing; the WS-Discovery responder
(that is sdc-biceps); a nightly job.

---
## Epic context — static-fuzz-ci

See the epic `README.md`. Depends only on task 2. Closes the epic.
