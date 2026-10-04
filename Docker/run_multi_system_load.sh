#!/usr/bin/env bash
# Smoke-at-scale gate for the multi-system reference's load harness
# (multi-system-reference / load-harness task 4). Opt-in, ~3 minutes, not in
# the default suite:
#
#   throwaway PostgreSQL -> station (pooled) + one stream edge -> spawn.py with
#   50 edge + 50 handheld JVM load clients (+ 2 guests) for 60 s -> report.py
#
# It passes when no client crashed, no rows were lost (DB rows == successful
# creates) and the only errors are the guests' deliberate PERMISSION_DENIED
# creates. This proves the harness works. It is NOT a benchmark: the numbers
# from one Docker container on a dev box mean nothing about real hardware.
#
#   Docker/run_multi_system_load.sh
#   EDGES=20 HANDHELDS=20 DURATION=30 Docker/run_multi_system_load.sh
#
# Output (summary.md, every client's JSONL and log) is left in
# build/multi_system_load/. Same throwaway-Postgres pattern as
# run_pg_tests.sh; container and network names carry this shell's PID so two
# runs don't collide.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$REPO_ROOT/Docker/_env.sh"

NET="harpia-msload-$$"
PG="harpia-msload-pg-$$"
PG_IMAGE="${HARPIA_PG_IMAGE:-postgres:16-alpine}"
DSN="host=${PG} dbname=harpiadb user=harpia password=harpiapass"

cleanup() {
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

harpia_ensure_image
docker network create "$NET" >/dev/null

# max_connections well above station's --pool (16) so the pool, not Postgres,
# is the limit under test
docker run -d --name "$PG" --network "$NET" \
    -e POSTGRES_USER=harpia -e POSTGRES_PASSWORD=harpiapass -e POSTGRES_DB=harpiadb \
    "$PG_IMAGE" -c max_connections=200 >/dev/null

echo "harpia: waiting for postgres..." >&2
for _ in $(seq 1 60); do
    docker exec "$PG" pg_isready -U harpia -d harpiadb >/dev/null 2>&1 && break
    sleep 1
done

docker run --rm --network "$NET" \
    -u "$(id -u):$(id -g)" \
    -v "$REPO_ROOT":/harpia \
    -v "$HARPIA_GRADLE_VOLUME":/tmp/.gradle \
    -w /harpia \
    -e HOME=/tmp \
    -e GRADLE_USER_HOME=/tmp/.gradle \
    -e HARPIA_PG_DSN="$DSN" \
    -e EDGES -e HANDHELDS -e GUESTS -e DURATION -e RAMP -e RATE \
    --ulimit nofile=65536:65536 \
    "$HARPIA_IMAGE" \
    python3 UnitTests/run_multi_system_load.py
