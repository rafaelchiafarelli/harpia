#!/usr/bin/env bash
# Build the harpia toolchain image (if needed) and run a command inside it with
# the repository mounted at /harpia. The host is never modified.
#
#   docker/run.sh                       # interactive shell
#   docker/run.sh pytest tests/         # run the test suite
#   docker/run.sh python3 main.py       # run the full pipeline
set -euo pipefail

IMAGE=harpia-build
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build -t "$IMAGE" "$REPO_ROOT"

# Run as the host user so files written into the mounted tree (generated C++,
# build/) are owned by you, not root. The named volume persists Gradle's
# dependency cache (~/.gradle = /tmp/.gradle, HOME=/tmp) across separate
# `docker run --rm` invocations -- otherwise every run starts from a cold
# Maven Central cache for the Java gradle+JDK-gated tests.
docker run --rm -it \
    -u "$(id -u):$(id -g)" \
    -v "$REPO_ROOT":/harpia \
    -v harpia-gradle-cache:/tmp/.gradle \
    -w /harpia \
    -e HOME=/tmp \
    -e GRADLE_USER_HOME=/tmp/.gradle \
    "$IMAGE" \
    "${@:-bash}"
