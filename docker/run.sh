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
# build/) are owned by you, not root.
docker run --rm -it \
    -u "$(id -u):$(id -g)" \
    -v "$REPO_ROOT":/harpia \
    -w /harpia \
    -e HOME=/tmp \
    "$IMAGE" \
    "${@:-bash}"
