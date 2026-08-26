# docker — one-shot toolchain image + run wrapper

**Role:** Reproducible build/test environment. `run.sh` builds the harpia toolchain image (from the repo-root `Dockerfile`) and runs any command inside it with the repo mounted at `/harpia`. The host is never modified.

## Contents
- `run.sh` — general-purpose entry point. Builds image then `docker run`s the given command (default `bash`).
- `run_android_emulator_tests.sh` + `_android_emulator_test_entrypoint.sh` — boots a headless Android emulator (hardware-accelerated via `/dev/kvm`) inside the image and runs `examples/android_consumer`'s three `connectedAndroidTest`s against it. Needs `/dev/kvm` on the host (nested virt enabled, if the host itself is a VM). See `examples/android_consumer/README.md` and the Dockerfile's Android SDK comment block for what's baked in vs. wired in at `docker run` time.

## Key facts / gotchas
- **Image tag:** `harpia-build` (`IMAGE=harpia-build`). Built with `docker build -t harpia-build <repo-root>` — the Dockerfile lives at the repo root, not here.
- Repo mounted at `/harpia` (`-w /harpia`); runs as the host user (`-u $(id -u):$(id -g)`) so generated C++ / `build/` are owned by you, not root. `HOME=/tmp`.
- Usage:
  - `docker/run.sh` — interactive shell
  - `docker/run.sh pytest tests/` — run the test suite
  - `docker/run.sh python3 main.py` — run the full generator pipeline
- **Non-TTY gotcha:** `run.sh` hard-codes `docker run --rm -it`. `-it` requires a TTY; in a non-interactive/CI/agent shell `docker run -it` errors with "the input device is not a TTY". When running non-interactively, invoke docker directly without `-t` (keep `-i` or drop both) rather than via `run.sh`, or run `run.sh` under a TTY.
