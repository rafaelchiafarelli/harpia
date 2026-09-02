# Static / fuzz analysis CI

**Done 2026-09-01 — all 5 tasks (1, 2, 3, 4a, 4b).** `cppcheck`
warning/portability gate over the generated tree + one hand-rolled
ASan/UBSan fuzz driver (`UnitTests/fuzz/`) covering the JSON, XML and SOAP
parser entry points, bounded + deterministic, `@pytest.mark.fuzz`, running
in the Docker suite. Task 4 was split into **4a** (extract the SOAP parse
seam into `SoapAdapter/runtime/harpia_soap.h` — it had no standalone
entry point) + **4b** (fuzz it); 4a is the epic's one generator-source +
golden change. Full suite green at the merge-up.

Planning was complete 2026-09-01 — originally four task files, "pure
tooling, no generator change" (held for tasks 1–3; task 4a needed the SOAP
seam extraction). No dependency on any other epic or on Foundation.

No cross-variant parity gate — dropped per `harpia_medical_master_plan.md`
§0a (one project-wide `risk_class` floor, no per-jurisdiction build
variants left to diff).

## Decided (do not re-litigate)

- **2026-09-01 — harness shape: `shutil.which`-gated pytest tests**, not a
  new CI system. This repo has no `.github/workflows/`; "CI" is
  `Docker/run.sh pytest`. Each job is a test module that shells out to the
  tool and `skipif`s when the tool is absent — exactly the pattern
  `test_doxygen_docs.py` already uses for `doxygen`. Runs inside the
  existing Docker suite.
- **2026-09-01 — static analysis: `cppcheck` core checks.** Not
  `clang-tidy` (needs a compile database + the full clang toolchain, a
  large image add). `cppcheck` is small, standalone, added to the Docker
  image apt list (same pattern as `git` for the versioning epic).
  **Revised during task 1 implementation:** the `cppcheck` `cert` addon
  was removed upstream and is absent from the Ubuntu package, so the job
  runs cppcheck's built-in `warning,portability` analysis — the practical
  stand-in for the CERT ruleset — rather than a CERT-tagged addon. A
  follow-on can add `clang-tidy` / `libFuzzer` / `style`-level tightening
  if this proves insufficient — noted, not scoped.
- **2026-09-01 — fuzzing: a hand-rolled bounded loop, g++ + ASan/UBSan.**
  Not `libFuzzer` (needs clang). A small C++ driver reads a checked-in
  seed corpus, applies a seeded (reproducible) bit-flip mutator for N
  iterations per target, and calls the parser entry point; built with
  `-fsanitize=address,undefined`. The three parser entry points are clean
  `bool f(const std::string&, Message*)` signatures — no sockets.
- **2026-09-01 — bounded + deterministic.** Default 5000 iterations per
  target (env-overridable), fixed PRNG seed so any crash reproduces. The
  fuzz tests carry a `@pytest.mark.fuzz` marker so `pytest -m "not fuzz"`
  skips them; they still run by default in the full Docker suite (target:
  a few seconds each, not minutes).
- **2026-09-01 — baseline, not a cleanup.** Task 1 delivers the harness
  plus a **checked-in suppression baseline** of every finding present in
  the current codebase, each with a one-line reason. Actually *resolving*
  a finding class is out of scope — if the first run surfaces a large
  count, spin those out as separate follow-on tasks rather than letting
  task 1 balloon.

## Receives

- **Nothing.** No Foundation dependency, no other epic.

## Gives

- A `cppcheck` `warning,portability` static-analysis pytest job over the
  generated C++ headers (the runtime headers included via the generated
  tree), failing on any **new** finding not in the checked-in baseline.
- Three fuzz-harness pytest jobs (JSON / XML / SOAP parsers), each running
  N iterations against a seed corpus with no ASan/UBSan crash.
- **Consumed by:** nobody as a build dependency — a CI safety net that
  validates every code-producing epic's output. No epic is gated on it.

## Tasks

| # | File | Delivers | Adds to image |
|---|---|---|---|
| 1 | `tasks/1-cppcheck-cert-static-analysis.md` | **done** — `cppcheck --enable=warning,portability` pytest job (`test_cppcheck.py`) over every generated `cpp/` header; empty baseline (tree is clean); no CERT addon (removed upstream). | `cppcheck` |
| 2 | `tasks/2-fuzz-harness-json-parser.md` | **done** — the shared fuzz driver (`UnitTests/fuzz/`, in-process `FuzzMsg` descriptor) + the JSON-parser target (`harpia::serialize::detail::from_json`) + 8-file seed corpus + `test_fuzz_parsers.py`. | — |
| 3 | `tasks/3-fuzz-harness-xml-parser.md` | **done** — the XML-parser target (`harpia::xml::from_xml`) + 10-file seed corpus, on task 2's driver. | — |
| 4a | `tasks/4a-extract-soap-parse-seam.md` | `SoapAdapter/runtime/harpia_soap.h` (pure Envelope→Body→message parse), `soap.h.tmpl` rewired to it, golden re-blessed. **The one task with a generator-source + golden footprint.** | — |
| 4b | `tasks/4b-fuzz-harness-soap-parser.md` | the SOAP-parser target (`harpia::soap::message_from_request`) + seed corpus, on task 2's driver. | — |

Task 2 carries the shared driver; 3 and 4b are thin additions once their
prerequisite has merged. Task 4 was split into 4a (extract the parse seam
— it had no standalone string→message entry point) + 4b (fuzz it) on
2026-09-01. Task 1 is fully independent of 2–4b.

## Files this epic touches

- `UnitTests/` (new: `test_cppcheck.py`, `cppcheck_suppressions.txt`,
  `test_fuzz_parsers.py`, `fuzz/harpia_fuzz_main.cpp`,
  `fuzz/corpus/{json,xml,soap}/`), `Dockerfile` (one apt entry, task 1).
- **Task 4a only:** `SoapAdapter/runtime/harpia_soap.h` (new),
  `Database/SoapAdapter.py`, `Database/templates/soap.h.tmpl`,
  `UnitTests/run_pipeline.py`, and `UnitTests/golden/soap/` (re-blessed).
  Tasks 1–3 touch no generator source and no golden.

## Watch for

- `cppcheck` and the fuzz builds need the generated tree — run
  `UnitTests/run_pipeline.py` into a tmp dir first (same as the golden and
  stage tests), don't point the tools at a stale `build/`.
- Keep the fuzz iteration budget bounded — the full Docker suite is
  already ~12 min; these must add seconds, not minutes. The deep run is a
  future nightly/opt-in concern, not this epic.
