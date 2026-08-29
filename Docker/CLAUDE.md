# docker — one-shot toolchain image + run wrapper

**Role:** Reproducible build/test environment. `run.sh` builds the harpia toolchain image (from the repo-root `Dockerfile`) and runs any command inside it with the repo mounted at `/harpia`. The host is never modified.

## Contents
- `_env.sh` — sourced by all three entrypoints below. Derives `HARPIA_IMAGE` (per-Dockerfile tag) and `HARPIA_GRADLE_VOLUME` (per-clone Gradle cache) and defines `harpia_ensure_image` (build only if that exact tag is missing). See "Concurrent clones" below.
- `run.sh` — general-purpose entry point. Ensures the image, then `docker run`s the given command (default `bash`).
- `run_android_emulator_tests.sh` + `_android_emulator_test_entrypoint.sh` — boots a headless Android emulator (hardware-accelerated via `/dev/kvm`) inside the image and runs `HarpiaTest/app_example/android_consumer`'s three `connectedAndroidTest`s against it. Needs `/dev/kvm` on the host (nested virt enabled, if the host itself is a VM). See `HarpiaTest/app_example/android_consumer/README.md` and the Dockerfile's Android SDK comment block for what's baked in vs. wired in at `docker run` time.

(`run_harpia.sh` at the repo root — the generate-a-project wrapper — sources `_env.sh` too.)

## Concurrent clones (why `_env.sh` exists)
Several harpia working copies run on one host at once (one per parallel session). Two shared, unqualified Docker names used to make that unsafe; `_env.sh` derives both:

- **`HARPIA_GRADLE_VOLUME`** — default `harpia-gradle-cache-<12hex sha256 of the clone's absolute path>`. Gradle takes an **exclusive** lock on `GRADLE_USER_HOME`, so two clones sharing one `harpia-gradle-cache` volume for the Java-target tests deterministically fail with `Timeout waiting to lock ... currently in use by another Gradle instance`. One warm, persistent cache **per clone** removes the shared lock. (Cost: N clones → N volumes; `docker volume ls | grep harpia-gradle-cache` then `docker volume rm` the stale ones, or `docker volume prune`.)
- **`HARPIA_IMAGE`** — default `harpia-build:<12hex sha256 of Dockerfile + .dockerignore>`. `docker build -t harpia-build` from a clone whose branch changed the Dockerfile used to silently repoint the tag for every other clone. Same Dockerfile content across clones → one shared image, built once (layer cache makes the extra tag ~free); a changed Dockerfile → its own tag, no clobber. Concurrent first-time builds of the same tag converge (BuildKit dedups), so no cross-clone lock is needed.

Export either var to override (pin a fixed image name, or deliberately share one Gradle cache). There is **no** auto-maintained `harpia-build:latest` anymore — use `Docker/run.sh`, or `HARPIA_IMAGE=... ` / `. Docker/_env.sh; echo "$HARPIA_IMAGE"` to get the tag.

## Key facts / gotchas
- **Dockerfile** lives at the repo root, not here. `_env.sh` needs `REPO_ROOT` set before it is sourced.
- Repo mounted at `/harpia` (`-w /harpia`); runs as the host user (`-u $(id -u):$(id -g)`) so generated C++ / `build/` are owned by you, not root. `HOME=/tmp`, `GRADLE_USER_HOME=/tmp/.gradle`.
- Usage:
  - `Docker/run.sh` — interactive shell
  - `Docker/run.sh pytest UnitTests/` — run the test suite
  - `Docker/run.sh python3 main.py` — run the full generator pipeline
- **TTY:** `run.sh` passes `-t` only when stdin **and** stdout are terminals, so it works unchanged in non-interactive / CI / agent shells (a bare `docker run -it` there errors with "the input device is not a TTY"). No need to hand-roll the `docker run` line anymore.
- The opt-in live-Postgres tests (`test_stage8_pg.py`, `test_java_db_crudl_postgres.py`) spin up a `--name harpia-pg` container on a `harpia-pg-net` network per their docstrings — those fixed names collide if two sessions set them up at once; give them per-session suffixes if you need concurrent PG runs.
