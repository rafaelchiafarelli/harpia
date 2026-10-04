# CI Pipeline: Turning "Ran Locally In Docker Once" Into an Actual Gate

**Status: scoped, not started.**

## 1. Why this exists

There is no CI at all — zero `.github/workflows`. Every "N passed" claim in a
commit message is a self-reported local run; nothing independently re-verifies
it, and nothing stops a regression from landing on `dev` or `main`. This isn't
a tooling gap so much as a wiring gap: `Dockerfile` already builds the entire
reproducible toolchain (protoc, gRPC, ZMQ, SOCI, DDS built from source, JDK 17
+ Gradle 8.5), and `Docker/run.sh pytest UnitTests/` already runs the whole
suite in one command, exactly the way a human runs it locally. CI is "invoke
what already exists on every push," not new infrastructure.

## 2. Scope

**In scope, now:** one epic, `github-actions`:
- A workflow that builds the toolchain image and runs the standard suite
  (`Docker/run.sh pytest UnitTests/`) on push/PR against `dev` and `main`.
- Docker layer caching, so the image — which includes an Android SDK install
  and a from-source DDS build, both genuinely slow — isn't rebuilt cold on
  every run.

**Out of scope, deferred:**
- **Android emulator tests** (`Docker/run_android_emulator_tests.sh`). Needs
  `/dev/kvm`; GitHub-hosted Ubuntu runners can expose nested KVM but it's
  slower and flakier than the base suite. Worth a follow-up epic once the base
  gate is green and boring, not bundled in here.
- **Opt-in live-Postgres tests** (`Docker/run_pg_tests.sh`,
  `test_stage8_pg.py`, `test_java_db_crudl_postgres.py`). These already skip
  cleanly without a live server (same toolchain-gated-skip posture as
  protoc/g++), so the base workflow gets them for free as skips; actually
  running them against a real Postgres service container is a separate,
  later epic if wanted.
- **Branch protection / required status checks.** Making the new check
  actually block merges is a GitHub repository-settings change (admin-only),
  not code — flag to Rafael once the workflow is green a few times in a row,
  don't wire it in as part of this initiative.

## 3. Non-goals

Not a coverage initiative — this doesn't add tests, it makes the ones that
already exist independently verifiable. Not a speed initiative beyond "don't
rebuild the image from scratch every run" — no attempt to parallelize the
suite itself or shard it across jobs.

## 4. Epics

One epic: **`github-actions`** (`epics/README.md`).

## 5. Verification approach

The workflow's own green run *is* the verification — there's no separate test
suite for a test suite. Each task's DoD is "a real GitHub Actions run on this
branch is green (or fails for a real, pre-existing reason, e.g. a genuinely
missing pkg-config on host — matches the 6 known host-only failures already
called out in `assessment-harpia.md`)."
