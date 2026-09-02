#!/usr/bin/env bash
# Runs the 4 opt-in live-PostgreSQL tests against a throwaway Postgres server:
#
#   UnitTests/test_stage8_pg.py               (C++ SOCI/libpq CRUDL + retype migration)
#   UnitTests/test_java_db_crudl_postgres.py  (Java/JDBC driver wiring + CRUDL cycle)
#
# These two files are skipped by the normal `Docker/run.sh pytest` run because
# they need HARPIA_PG_DSN pointing at a reachable server (see each file's
# module docstring). This script stands one up in a container, points the
# tests at it over a user-defined network, and tears it all down after.
#
# Nothing is installed on the host; the Postgres image is pulled on first use.
#
#   Docker/run_pg_tests.sh                 # run all 4
#   Docker/run_pg_tests.sh -k roundtrip    # extra args are passed through to pytest
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$REPO_ROOT/Docker/_env.sh"

NET=harpia-pgtest
PG=harpia-pg
PG_IMAGE="${HARPIA_PG_IMAGE:-postgres:16-alpine}"
DSN="host=${PG} dbname=harpiadb user=harpia password=harpiapass"

cleanup() {
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup   # clear any leftovers from an interrupted previous run

harpia_ensure_image
docker network create "$NET" >/dev/null

docker run -d --name "$PG" --network "$NET" \
    -e POSTGRES_USER=harpia -e POSTGRES_PASSWORD=harpiapass -e POSTGRES_DB=harpiadb \
    "$PG_IMAGE" >/dev/null

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
    "$HARPIA_IMAGE" \
    pytest UnitTests/test_stage8_pg.py UnitTests/test_java_db_crudl_postgres.py "$@"
