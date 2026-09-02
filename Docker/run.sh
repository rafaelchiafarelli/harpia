#!/usr/bin/env bash
# Build the harpia toolchain image (if needed) and run a command inside it with
# the repository mounted at /harpia. The host is never modified.
#
#   Docker/run.sh                       # interactive shell
#   Docker/run.sh pytest UnitTests/         # run the test suite
#   Docker/run.sh python3 main.py       # run the full pipeline
#
# Safe to run from several clones at once: the image tag and the Gradle cache
# volume are per-Dockerfile / per-clone (see Docker/_env.sh; override with
# HARPIA_IMAGE / HARPIA_GRADLE_VOLUME).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$REPO_ROOT/Docker/_env.sh"

harpia_ensure_image

# -t only when stdin AND stdout are real terminals, so this works unchanged in
# non-interactive / CI / agent shells (where `docker run -it` errors with "the
# input device is not a TTY").
tty_flags=(-i)
if [ -t 0 ] && [ -t 1 ]; then tty_flags=(-i -t); fi

# Run as the host user so files written into the mounted tree (generated C++,
# build/) are owned by you, not root. HARPIA_GRADLE_VOLUME persists Gradle's
# dependency cache (~/.gradle = /tmp/.gradle, HOME=/tmp) across separate
# `docker run --rm` invocations -- otherwise every run starts from a cold
# Maven Central cache for the Java gradle+JDK-gated tests -- without sharing
# Gradle's exclusive lock with another clone.
docker run --rm "${tty_flags[@]}" \
    -u "$(id -u):$(id -g)" \
    -v "$REPO_ROOT":/harpia \
    -v "$HARPIA_GRADLE_VOLUME":/tmp/.gradle \
    -w /harpia \
    -e HOME=/tmp \
    -e GRADLE_USER_HOME=/tmp/.gradle \
    "$HARPIA_IMAGE" \
    "${@:-bash}"
