# ci-pipeline — epics

One epic: **`github-actions`** (`github-actions/tasks/`).

## Task order

```
1-workflow-skeleton
        │
        ▼ (needs a working workflow to cache)
2-image-layer-caching
```

## Definition of done (every task)

- A real GitHub Actions run on the task's branch, visible in the repo's
  Actions tab, either green or red for a genuine pre-existing reason (not a
  workflow authoring bug).
- No change to `Dockerfile`, `Docker/run.sh`, or test behavior — this epic
  wires CI to what already exists, it doesn't change what "passing" means.
  If a task discovers the suite genuinely doesn't pass in a clean
  (non-Docker-`run.sh`, no leftover host state) environment, stop and flag it
  rather than loosening the workflow to hide it.

## Watch for

- **`Docker/_env.sh`'s per-clone image tag** (`harpia-build:<sha256 of
  Dockerfile+.dockerignore>`) is designed around concurrent local clones on
  one host, not CI. A CI runner is a fresh VM per run, so `HARPIA_IMAGE`'s
  default naming is harmless there, but task 2's caching key should hash the
  same two files (`Dockerfile` + `.dockerignore`) so a cache hit/miss lines
  up with whether the image actually needs rebuilding — don't invent a
  separate cache-key scheme.
- **TTY handling in `run.sh`** is already CI-safe (`-t` only when both stdin
  and stdout are real terminals) — no changes needed there.
- **Gated tests must stay gated, not skipped by omission.** The workflow
  should show the same ~132 toolchain-gated skips a clean Docker run already
  produces, not silently exclude a test file. If a task's run reports 0
  skips or a wildly different count than what `Docker/run.sh pytest
  UnitTests/` reports locally, treat that as a workflow bug to fix, not a
  result to accept.
