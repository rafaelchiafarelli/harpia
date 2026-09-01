# Static / fuzz analysis CI

Planning complete 2026-09-01 — four task files under `tasks/`. Pure
tooling: no generator change, no golden movement, no dependency on any
other epic or on Foundation. Every task is independent — pick up any of
them whenever a session-line has a gap.

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
- **2026-09-01 — static analysis: `cppcheck` with its CERT addon.** Not
  `clang-tidy` (needs a generated-project compile database + the full
  clang toolchain, a large image add). `cppcheck` is small, standalone,
  added to the Docker image apt list (same pattern as `git` for the
  versioning epic). A follow-on epic can add `clang-tidy` / `libFuzzer`
  later if the `cppcheck` + g++/ASan coverage proves insufficient — noted,
  not scoped.
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

- A `cppcheck`/CERT static-analysis pytest job over the generated C++ tree
  + the hand-written runtime headers, failing on any **new** finding above
  the agreed severity (baseline suppressed).
- Three fuzz-harness pytest jobs (JSON / XML / SOAP parsers), each running
  N iterations against a seed corpus with no ASan/UBSan crash.
- **Consumed by:** nobody as a build dependency — a CI safety net that
  validates every code-producing epic's output. No epic is gated on it.

## Tasks

| # | File | Delivers | Adds to image |
|---|---|---|---|
| 1 | `tasks/1-cppcheck-cert-static-analysis.md` | `cppcheck` + CERT addon pytest job over generated + runtime C++; checked-in suppression baseline; acceptance gate = clean/triaged run. | `cppcheck` |
| 2 | `tasks/2-fuzz-harness-json-parser.md` | the shared fuzz driver (`UnitTests/fuzz/`) + the JSON-parser target (`harpia::serialize::from_json`) + seed corpus. | — |
| 3 | `tasks/3-fuzz-harness-xml-parser.md` | the XML-parser target (`harpia::xml::from_xml`) + seed corpus, on task 2's driver. | — |
| 4 | `tasks/4-fuzz-harness-soap-parser.md` | the SOAP-parser target + seed corpus, on task 2's driver. | — |

Task 2 carries the shared driver; 3 and 4 are thin additions once 2 has
merged. Task 1 is fully independent of 2–4.

## Files this epic touches

- `UnitTests/` (new: `test_cppcheck_cert.py`, `cppcheck_suppressions.txt`,
  `test_fuzz_parsers.py`, `fuzz/harpia_fuzz_main.cpp`,
  `fuzz/corpus/{json,xml,soap}/`), `Dockerfile` (one apt entry, task 1).
- **No** generator source, **no** `UnitTests/golden/`.

## Watch for

- `cppcheck` and the fuzz builds need the generated tree — run
  `UnitTests/run_pipeline.py` into a tmp dir first (same as the golden and
  stage tests), don't point the tools at a stale `build/`.
- Keep the fuzz iteration budget bounded — the full Docker suite is
  already ~12 min; these must add seconds, not minutes. The deep run is a
  future nightly/opt-in concern, not this epic.
