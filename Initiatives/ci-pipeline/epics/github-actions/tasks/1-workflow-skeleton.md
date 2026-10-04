## GitHub Actions workflow running the standard suite

- **Depends on:** nothing (existing shipped `Dockerfile` + `Docker/run.sh`).
- **Deliverable:** `.github/workflows/ci.yml` on a GitHub-hosted
  `ubuntu-latest` runner:
  - Triggers: `push` to `dev` and `main`, and `pull_request` targeting either.
  - Steps: checkout, `docker build -t harpia-build .` (or reuse
    `Docker/_env.sh`'s `harpia_ensure_image` so the tag scheme matches local
    runs), then `Docker/run.sh pytest UnitTests/` (or the equivalent `docker
    run` invocation `run.sh` wraps — either is fine as long as it's the same
    command a human runs locally, not a hand-rolled subset).
  - Job fails (non-zero exit) iff pytest reports a failure. Skips (toolchain-
    gated tests without protoc/g++ present on host — not relevant here since
    the image always has them, so skips here should only be the small
    genuinely-host-only set, if any) are not failures.
  - No matrix, no parallel shards — one job, one run, matching how the suite
    is run locally today.
- **Out of scope:** image caching (task 2), Android emulator tests, live-
  Postgres tests, branch protection wiring.
- **Verification:** push this branch, open the Actions tab, confirm a real
  run completes and its pass/fail matches a local
  `Docker/run.sh pytest UnitTests/` run on the same commit (compare pass/
  skip/fail counts, don't just eyeball green/red).
