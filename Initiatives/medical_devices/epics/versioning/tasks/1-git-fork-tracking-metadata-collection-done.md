## Git fork-tracking metadata collection

Scoped 2026-09-01. Task 1 of the versioning epic: a self-contained helper
that reads the active git state at generation time and returns it in a
fixed shape. Task 2 wires the result into `ComplianceReport/`'s `bom.json`.
This task ships **nothing user-visible on its own** — no pipeline stage
change, no output-file change. It is the collection primitive plus its
tests.

### Decisions (settled during scoping — do not re-litigate)

- **Mechanism: shell out to the `git` binary via `subprocess`.** Not a
  hand-rolled `.git/` reader — `merge-base` (the fork-point field) is not
  feasible without the binary, and `git` handles worktrees / packed-refs /
  detached HEAD / submodules for free.
- **`git` becomes a Docker image dependency.** Add `git` to the
  `apt-get install` list in `Dockerfile` (~line 80). This reverses the
  sbom-emission task's "no Docker image change" stance, deliberately, so the
  task-2 integration tests ("stamp matches actual git state", "fork →
  traceable to parent") can run in canonical CI instead of only on a dev
  host. One-time rebuild per clone; `Docker/run.sh` tags per-Dockerfile so
  it picks the new image automatically.
- **Graceful absence is still a contract, not a fallback.** When `git` is
  missing (`FileNotFoundError`), the directory is not a repo, a subcommand
  exits non-zero, or a field simply doesn't apply (no remote), that field
  is the string `"unknown"` — never omitted, never fabricated, never a
  raise. Matches the `harpia:crypto_backend` → `"unknown"` precedent.
- **Which repo's state:** the *schema project* being generated, not the
  generator. Discover the git root by walking up from the input `.harpia`
  file's directory; fall back to `os.getcwd()` if that isn't under a repo.
  (In this codebase the two coincide — `HarpiaTest/` lives in the generator
  repo — but the field semantics are "the project a user forked".)
- **Fixed six-field shape**, all values `str` or `bool`:
  | key | source | absent value |
  |---|---|---|
  | `commit` | `git rev-parse HEAD` | `"unknown"` |
  | `ref` | `git symbolic-ref --short -q HEAD`, else `git describe --tags --exact-match`, else `"unknown"` | `"unknown"` |
  | `dirty` | `git status --porcelain` non-empty → `True`; empty → `False` | `"unknown"` (a real `str`, not a bool, when git unavailable) |
  | `describe` | `git describe --tags --always --dirty` | `"unknown"` |
  | `origin_url` | `git config --get remote.origin.url` | `"unknown"` |
  | `parent_commit` | `git merge-base HEAD origin/HEAD` (the fork point) | `"unknown"` |
- **No network.** Every subcommand is local — `merge-base` against
  `origin/HEAD` reads the existing local ref, never fetches. If
  `origin/HEAD` doesn't resolve, `parent_commit` is `"unknown"`.
- **Module location:** new `Util/gitstate.py` (one cohesive, independently
  testable module) rather than accreting onto `Util/util.py`, whose own
  header discourages growth. `Util/CLAUDE.md` gets a short entry.
- **Not split.** Collection helper + Dockerfile line + tests is one
  contract.

### Contract

**In:**
- `collect_git_state(start_path=None) -> dict` in `Util/gitstate.py`.
  `start_path` defaults to `os.getcwd()`; callers (task 2) pass the input
  schema file's directory.

**Required:** F1 merged (shipped). Nothing from any other epic. Nothing
from task 2 (task 2 depends on this).

**Delivered (the contract task 2 builds on):**
- `Util/gitstate.py::collect_git_state(start_path=None) -> dict` returning
  exactly the six keys above, in a stable insertion order, every call.
  - Pure read. No writes, no env mutation, no `chdir` (pass `cwd=` to
    `subprocess`, restore nothing).
  - Every subcommand independently guarded: a failure of one field never
    affects another. `git` binary absent → all six `"unknown"`
    (`dirty` included, as the string `"unknown"`), returns normally.
  - Deterministic for a fixed repo state.
  - A module-level indirection point so task 2's tests can monkeypatch it
    (e.g. `collect_git_state` referenced through the module object, same
    pattern as `ComplianceReport._rfc3339_now`).
- `Dockerfile`: `git` added to the `apt-get install -y` list.
- `Util/CLAUDE.md`: one bullet under "Public functions" (note it lives in
  `gitstate.py`, not `util.py`).

**Pre-work (all inside this task; none needs separate scoping):**
- None. No `.harpia` fixture (git state is schema-independent). No golden
  movement (this task writes no generated output). The Dockerfile line is
  part of this task's implementation, not pre-work.

**Tests** — new `UnitTests/test_gitstate.py`, pure Python, always run:
- Against the harpia repo itself (the test process runs inside a checkout):
  `collect_git_state()["commit"]` equals `git rev-parse HEAD` captured
  independently; `ref` and `describe` are non-`"unknown"`; the result has
  exactly the six expected keys.
- `tmp_path` that is not a git repo → all six values `"unknown"`, no
  exception.
- `git` binary simulated absent (monkeypatch `subprocess.run` /
  `shutil.which` to raise `FileNotFoundError`) → same all-`"unknown"`
  dict, no exception.
- `git init` a `tmp_path` + one commit, no remote configured →
  `commit` / `ref` / `describe` are real values; `origin_url` and
  `parent_commit` are `"unknown"`.
- `dirty`: in a `git init` tmp repo, `False` on a clean tree, `True` after
  touching an untracked/modified file.
- `skipif(shutil.which("git") is None)` on the cases that need a real
  `git` — same gating discipline as the protoc/cmake tests — so a bare
  host without git stays green on the graceful-absence cases alone.

**Out of scope (task 2):** any change to `ComplianceReport.py`, `bom.json`,
`requirements.py`, `run_pipeline.py`, or the golden snapshots; the
`HARPIA_TOOL_VERSION` bump; the fork/lineage integration tests that drive
the whole pipeline.

---
## Epic context — versioning

**Contract.** Git fork-tracking metadata (commit, ref, dirty, describe,
origin, fork-point) emitted as fields **within** the process-artifacts
epic's existing `ComplianceReport/`/SBOM output — "one more field in
something it already emits," not a new registry or sidecar file
(decided 2026-08-23; the continuable-process registry this epic originally
targeted was never built). Two tasks: (1) collect the git state
[this file]; (2) wire it into `bom.json`.

**Receives.** F1 (Foundation); the process-artifacts epic's sbom-emission
task merged (task 2 only — the `ComplianceReport/` module must exist to
extend). Both shipped.

**Files.** `Util/gitstate.py` (new), `Dockerfile` (one line) — this task.
`ComplianceReport/ComplianceReport.py`, `ComplianceReport/requirements.py`,
`UnitTests/run_pipeline.py`, `ComplianceReport/CLAUDE.md`, the
`compliancereport` golden — task 2.

**Watch for.** The versioning epic no longer touches `main.py`
orchestration (the old continuable-process-coupled scoping assumed it did)
— `ComplianceReport` is already wired in at pipeline step 15. Don't carry
the `main.py` assumption forward.
