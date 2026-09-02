## cppcheck static-analysis job

Scoped 2026-09-01. **Implemented 2026-09-01 — see the "Implementation
notes" below for two deviations from the original scoping.** Task 1 of
static-fuzz-ci, fully independent of tasks 2–4. A `shutil.which`-gated
pytest job that runs `cppcheck` over the generated C++ headers and fails
on any finding not in a checked-in baseline.

### Decisions (as implemented)

- **Tool: `cppcheck` core checks.** Added to the `Dockerfile` `apt-get`
  list. **No `--addon=cert`** — upstream cppcheck removed `cert.py`
  (~v2.7) and Ubuntu 24.04's cppcheck 2.13 does not ship it (confirmed on
  the image). The deliverable is cppcheck's built-in `warning,portability`
  analysis, which already covers much of CERT's memory-safety / integer
  intent. Not `clang-tidy` (needs a compile DB + the clang toolchain).
- **Harness: `UnitTests/test_cppcheck.py`** (not `_cert`), pytest,
  `skipif(shutil.which("cppcheck") is None)`. No GitHub Actions.
- **Analysis target:** every `.h` under the generated `cpp/` tree,
  produced by `UnitTests/run_pipeline.py` into a tmp dir. The hand-written
  runtime headers are **included via that tree** — they are copied into
  `generated/cpp/{serialize,xml,yaml,crypto,delivery,events,...}/` in
  their real relative layout, which is also what lets cppcheck's
  preprocessor resolve the intra-tree `#include "yaml/harpia_yaml.h"`
  paths (analysing the repo-source copies standalone yields only
  `syntaxError` noise). Files enumerated explicitly — cppcheck skips a
  bare directory that contains no `.cpp`. `third_party/` excluded.
- **Invocation:** `cppcheck --enable=warning,portability --language=c++
  --std=c++17 --inline-suppr -q --error-exitcode=2
  --suppressions-list=UnitTests/cppcheck_suppressions.txt <headers…>`.
  Non-zero exit fails the test with cppcheck's report.
- **Severity gate:** `warning` / `portability` gate. `style` is **off** —
  it produces 50+ pure-noise findings on generated CRUDL code
  (`shadowVariable` from reused `c0`/`l0` names, `useStlAlgorithm`
  opinions); `performance` / `information` likewise off. A follow-on task
  can tighten.
- **Baseline: `UnitTests/cppcheck_suppressions.txt`.** The current tree
  produces **zero** `warning`/`portability` findings, so the file carries
  only `missingInclude` / `missingIncludeSystem` (cppcheck has no
  protobuf/grpc/tinyxml2 include tree — not code defects). It exists so a
  *new* finding fails the gate, and any future confirmed false positive
  gets one line here with a reason on the comment line above it.
- **Scope is the harness + the baseline, not a cleanup** — held: the
  baseline is empty of real findings, no triage was needed.

### Implementation notes (deviations, approved 2026-09-01)

1. **No CERT addon** — removed upstream / absent from the package. Dropped
   the "CERT ruleset" label; the job is cppcheck's core `warning`/
   `portability` analysis. (Option considered and declined: vendoring an
   unmaintained `cert.py` from an old cppcheck tag.)
2. **cppcheck finds nothing real today** — `warning,portability` over the
   generated tree is clean. The value delivered is a **regression net**
   over future generated-code / runtime-header changes, not a backlog of
   findings to fix. `style`-level tightening and full include-graph
   plumbing so headers parse in isolation are both possible follow-ons,
   not in this task.

### Contract

**In:** `cppcheck` on PATH (Docker image after this task). The generator
pipeline (already present) to produce the tree under test.

**Required:** nothing from any epic or Foundation.

**Delivered:**
- `Dockerfile`: `cppcheck` in the apt list.
- `UnitTests/test_cppcheck.py`: generates the tree into `tmp_path`, walks
  every `.h` under `build/generated/cpp/`, runs the cppcheck invocation
  above, asserts exit 0 (fails with cppcheck's report otherwise).
  `skipif` when `cppcheck` is absent.
- `UnitTests/cppcheck_suppressions.txt`: the baseline (empty of real
  findings — only `missingInclude` / `missingIncludeSystem`), with a
  header explaining its purpose and that a new entry needs a reason.

**Pre-work:** none. No `.harpia` fixture, no golden. The suppression
baseline is authored *by this task* from the first real run — it is the
deliverable, not pre-work.

**Tests:** the pytest job *is* the test. Acceptance gate: a clean run
(exit 0) against the current codebase with the baseline in place, in
Docker, before the task is marked done. `HARPIA_UPDATE_...`-style
regeneration is not applicable (no golden).

**Out of scope:** `clang-tidy`; resolving any finding; `style`/`perf`
severities; a nightly deep run; analysing generated Java.

---
## Epic context — static-fuzz-ci

See the epic `README.md` for the full contract, the settled decisions
(pytest-gated harness, `cppcheck` + g++/ASan, bounded + deterministic
fuzzing, baseline-not-cleanup), and the files map. Tasks 1–4 are mutually
independent; task 1 shares nothing with the fuzz tasks.
