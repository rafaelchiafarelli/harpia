# Initiative: live test-suite progress for the helper scripts

**Status:** scoping doc only — not started. Raised 2026-08-29 after a
session spent eyeballing pytest dot-counts and lagging `[ NN%]` markers to
guess how far a ~11-minute Docker suite run had got, and whether anything
had failed yet.

## Problem

`Docker/run.sh pytest …`, `run_harpia.sh`, and the raw
`docker run … harpia-build pytest …` invocations give **no usable live
progress**:

- `pytest -q` streams one character per test (`.` pass, `F` fail, `s`
  skip, `x`/`X` xfail/xpass, `E` error) but buffers when its stdout is a
  pipe rather than a TTY — so a `| tee log` shows nothing until near the
  end unless `python -u` / `stdbuf -oL` forces line buffering.
- The `[ NN%]` marker pytest prints only updates once per full
  terminal-width line, so it lags the real position by up to a screen of
  tests, and its width depends on `COLUMNS` (meaningless with no TTY).
- The only exact number is the final `N passed, M skipped …` summary,
  which by definition arrives when the run is already over.

Net effect: for a 10–12 min suite you cannot tell 20 % from 90 %, or
whether test 140 already failed, without watching the whole thing. This
also overlaps with the recurring "is a suite even running right now?"
question when several clones share the machine.

## Signals already available (no code change)

| technique | gives | cost |
|---|---|---|
| `pytest --collect-only -q \| tail -1` | exact total up front | ~2–5 s pre-run |
| `python -u -m pytest … \| tee log` | live char stream | none |
| `tr -cd '.FsxE' < log \| wc -c` vs the total | rough % + pass/fail tally | fragile parsing |
| `-rA` / `-ra` | end-of-run reason list | not live |

The char-stream approach is what the raising session used by hand. It
works but is brittle: `pytest -q` also emits non-test characters (the
platform banner, `collected N items`, warnings summary), and any stray
ANSI colour (if a TTY sneaks in) corrupts the count. Parsing must anchor
after the `collected N items` line and stop at the first blank line.

## Options for the helper scripts

### A — wrapper + log parser, no pytest changes

`Docker/run.sh` gains a `--progress` mode (or a sibling `Docker/run-suite.sh`)
that: (1) runs `pytest --collect-only -q` for `$TOTAL`, (2) runs
`python -u -m pytest … | tee "$LOG"`, (3) a background reader counts
`[.FsxE]` in `$LOG` and prints
`NNN/$TOTAL (PP%)  pass=… fail=… skip=…  elapsed mm:ss` every second and
on exit.

- **Pros:** zero dependencies; works with today's `-q` output.
- **Cons:** char-stream parsing is fragile (see above); `%` drifts if
  `--collect-only` and the real run deselect differently (`-k`, `-m`,
  `-x` early-exit).

### B — `--report-log` JSONL, one dependency

pytest's `pytest-reportlog` plugin: `--report-log=$LOG.jsonl` writes one
JSON object per test phase as it finishes
(`{"$report_type":"TestReport","when":"call","outcome":"passed","nodeid":…}`).
Reader: `tail -f | jq -r 'select(.when=="call").outcome'` and tally.

- **Pros:** robust, structured, machine-readable; the same JSONL is a
  natural seed for later CI dashboards / flaky-test history.
- **Cons:** adds `pytest-reportlog` to the `Dockerfile` and the host
  `.venv`; total-count still needs `--collect-only` or counting `when ==
  "setup"` events.

### C — `conftest.py` progress hook, no dependency  *(recommended)*

Add `UnitTests/conftest.py`, **strictly opt-in via an env var** so a plain
`pytest` run is byte-for-byte unchanged:

```python
import os, json, time

_PF = os.environ.get("HARPIA_PROGRESS_FILE")

def pytest_collection_finish(session):
    if _PF:
        with open(_PF, "w") as f:
            f.write(json.dumps({"event": "collected",
                                "total": len(session.items),
                                "t": time.time()}) + "\n")

def pytest_runtest_logreport(report):
    # one line per test on its "call" phase, plus any non-passing
    # setup/teardown (skips, collection errors) so the tally is complete
    if not _PF:
        return
    if report.when == "call" or (report.when != "call" and report.outcome != "passed"):
        with open(_PF, "a") as f:
            f.write(json.dumps({"nodeid": report.nodeid,
                                "outcome": report.outcome,
                                "when": report.when,
                                "t": time.time()}) + "\n")
```

A reader (`Docker/suite-status.sh`): first line → `total`; remaining lines
→ `done = wc -l`, `% = done*100/total`, `failed = grep -c '"outcome": "failed"'`,
`elapsed = last t − first t`. Set `HARPIA_PROGRESS_FILE=/harpia/.suite-progress.jsonl`
in whichever helper runs the suite; `.gitignore` it. Works identically for
`Docker/run.sh`, the raw `docker run`, and host `.venv` runs.

- **Pros:** no new dependency; exact total from pytest's own collection;
  structured; sees setup/teardown outcomes; the reader doubles as the
  "is a suite running / how far" check the shared-machine one-liners only
  approximate.
- **Cons:** a new always-imported `conftest.py` under `UnitTests/`
  (currently none exists — config is `pytest.ini` only). Keep every code
  path behind the env-var guard and add a test that a plain run is
  unaffected and that the file appears only when the var is set.

### D — `pytest-sugar`

Live per-test progress bar. **Rejected:** needs a TTY (the
non-interactive `docker run` path has none since `run.sh`'s TTY
auto-detect), changes output format for every run, and adds a dependency.

## Recommendation

Option **C**: env-gated `UnitTests/conftest.py` hook + `Docker/suite-status.sh`
reader, plus a `Docker/run.sh --progress` (or `HARPIA_PROGRESS=1`) path that
sets the env var, tees, and prints a one-line final summary. Default
behaviour with the var unset is untouched.

## Sizing

Small. One epic, ~2 tasks:

1. **`progress-hook`** — `UnitTests/conftest.py` env-gated hook +
   `.gitignore` entry + a test asserting (a) a plain run is byte-identical
   and writes nothing, (b) with the var set the JSONL total matches the
   collected count and one line lands per test.
2. **`helper-integration`** — `Docker/suite-status.sh` reader,
   `Docker/run.sh --progress` wiring, and docs in `Docker/CLAUDE.md` +
   whatever `NEXT_SESSION.md` exists.

## Out of scope

- Changing default pytest output for anyone not asking for progress.
- CI dashboards / historical flaky-test tracking — option B's
  `--report-log` JSONL would be the seed; note it as a future extension of
  this initiative, not part of it.
- The Windows/PowerShell `Tee-Object` UTF-16 log-encoding gotcha — a
  separate, unrelated issue (these helper scripts are Linux/Docker; logs
  stay UTF-8).
