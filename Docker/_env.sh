# Shared Docker identity for every harpia entrypoint that builds/runs the
# toolchain image (Docker/run.sh, Docker/run_android_emulator_tests.sh,
# run_harpia.sh). Sourced, not executed.
#
# WHY THIS EXISTS -- concurrent working copies on one host
# -------------------------------------------------------
# Multiple harpia clones (one per parallel session) build and test at the same
# time. Two shared, unqualified Docker names used to make that unsafe:
#
#   * the Gradle cache volume `harpia-gradle-cache` -- Gradle takes an
#     EXCLUSIVE lock on GRADLE_USER_HOME, so two clones running the Java-target
#     tests against one volume deterministically fail with
#     "Timeout waiting to lock ... currently in use by another Gradle instance".
#
#   * the image tag `harpia-build` -- `docker build -t harpia-build` from a
#     clone whose branch changed the Dockerfile silently repoints the tag for
#     every other clone; the next `docker run harpia-build` elsewhere then uses
#     the wrong image.
#
# Both names are now derived so clones don't collide:
#
#   HARPIA_IMAGE           image ref to build / run
#                          default: harpia-build:<first-12-hex sha256 of the
#                          Dockerfile + .dockerignore>. Identical Dockerfile
#                          content across clones -> one shared image, built
#                          once (layer cache makes the extra tag ~free); a
#                          modified Dockerfile on some branch -> its own tag,
#                          no clobber.
#
#   HARPIA_GRADLE_VOLUME   docker volume mounted at /tmp/.gradle
#                          default: harpia-gradle-cache-<first-12-hex sha256 of
#                          this clone's absolute path>. One warm, persistent
#                          Gradle cache per clone; never a shared lock.
#
# Either can be exported by the caller to override the default (e.g. pin a
# fixed image name, or deliberately share one Gradle cache).
#
# Concurrency of the build itself needs no extra locking: `docker build` of the
# same ref from two clones converges on an identical result (BuildKit dedups),
# and `harpia_ensure_image` only builds when that exact ref is absent, so the
# race window is just the first-ever build of a given Dockerfile.
#
# shellcheck shell=bash

: "${REPO_ROOT:?Docker/_env.sh: REPO_ROOT must be set before sourcing}"
[ -f "$REPO_ROOT/Dockerfile" ] || {
    echo "Docker/_env.sh: no Dockerfile at REPO_ROOT ($REPO_ROOT)" >&2
    return 1 2>/dev/null || exit 1
}

_harpia_hash12() { sha256sum | cut -c1-12; }

if [ -z "${HARPIA_IMAGE:-}" ]; then
    _harpia_df_hash="$(
        { cat "$REPO_ROOT/Dockerfile"; cat "$REPO_ROOT/.dockerignore" 2>/dev/null || true; } \
            | _harpia_hash12
    )"
    HARPIA_IMAGE="harpia-build:${_harpia_df_hash}"
fi
export HARPIA_IMAGE

if [ -z "${HARPIA_GRADLE_VOLUME:-}" ]; then
    _harpia_clone_hash="$(printf '%s' "$REPO_ROOT" | _harpia_hash12)"
    HARPIA_GRADLE_VOLUME="harpia-gradle-cache-${_harpia_clone_hash}"
fi
export HARPIA_GRADLE_VOLUME

# Build the toolchain image only when this exact ref is missing.
harpia_ensure_image() {
    if ! docker image inspect "$HARPIA_IMAGE" >/dev/null 2>&1; then
        echo "harpia: building $HARPIA_IMAGE (first use for this Dockerfile)..." >&2
        docker build -t "$HARPIA_IMAGE" "$REPO_ROOT"
    fi
}
