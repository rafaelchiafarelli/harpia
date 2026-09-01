## cppcheck / CERT static-analysis job

Scoped 2026-09-01. Task 1 of static-fuzz-ci, fully independent of tasks
2–4. Stands up a `shutil.which`-gated pytest job that runs `cppcheck` with
its CERT addon over the generated C++ tree plus the hand-written runtime
headers, and fails on any finding not in a checked-in baseline.

### Decisions (settled during scoping — do not re-litigate)

- **Tool: `cppcheck` + `--addon=cert`.** Added to the `Dockerfile`
  `apt-get install` list (`cppcheck`; the CERT addon ships with the
  Ubuntu package). Not `clang-tidy`.
- **Harness: a pytest module** `UnitTests/test_cppcheck_cert.py`,
  `pytest.mark.skipif(shutil.which("cppcheck") is None)`. No GitHub
  Actions.
- **Analysis target:** (a) the generated C++ for `HarpiaTest/test.harpia`,
  produced by running `UnitTests/run_pipeline.py` into a tmp dir (same as
  the golden/stage tests — never a stale `build/`); (b) the checked-in
  hand-written runtime headers (`*/runtime/harpia_*.h` — serialize / xml /
  yaml / delivery / crypto / event-cache / dds-security / audit-sink /
  wsdiscovery). Vendored `third_party/` is excluded.
- **Severity gate:** `cppcheck` run with `--enable=warning,portability`
  and `--error-exitcode=2`; a finding of severity `error` or `warning`
  (including CERT-addon findings) fails the test. `style` / `information`
  / `performance` do not gate (too noisy for a first pass; a follow-on can
  tighten).
- **Baseline:** `UnitTests/cppcheck_suppressions.txt` — every finding
  present in the codebase at epic time, as a `cppcheck` suppression line
  (`<id>:<file>:<line>` or a bare `<id>` where line-stable), **each with a
  trailing `# reason` comment**. The test passes `--suppressions-list`.
  A new finding not covered by the baseline fails.
- **Scope is the harness + the baseline, not a cleanup.** If the first
  run surfaces a large finding count, the baseline still captures them all
  (test goes green) and resolving finding classes is spun out as separate
  follow-on tasks — task 1 does not absorb an open-ended cleanup.

### Contract

**In:** `cppcheck` on PATH (Docker image after this task). The generator
pipeline (already present) to produce the tree under test.

**Required:** nothing from any epic or Foundation.

**Delivered:**
- `Dockerfile`: `cppcheck` in the apt list.
- `UnitTests/test_cppcheck_cert.py`: generates the tree into `tmp_path`,
  runs `cppcheck --addon=cert --enable=warning,portability
  --suppressions-list=UnitTests/cppcheck_suppressions.txt
  --error-exitcode=2 --inline-suppr <generated dir> <runtime headers>`,
  asserts exit 0. On non-zero it fails with cppcheck's report in the
  message. `skipif` when `cppcheck` is absent.
- `UnitTests/cppcheck_suppressions.txt`: the triaged baseline, one
  `id:file:line  # reason` per line; a header comment explaining the
  file's purpose and that a new entry needs a reason.
- If the baseline is non-trivial, a short `## Findings baseline` section
  appended to the epic README summarizing the finding classes captured
  and pointing at any follow-on tasks created.

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
