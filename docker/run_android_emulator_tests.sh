#!/usr/bin/env bash
# Boots a headless Android emulator (hardware-accelerated via /dev/kvm) inside
# the harpia toolchain container and runs examples/android_consumer's three
# `connectedAndroidTest`s (J.25 message classes, J.26 gRPC client, J.27 ZMQ
# client) against it. The emulator + system image are baked into the image
# (Dockerfile) at build time; this script only wires in the one thing that
# can't be baked in -- hardware virtualization access (/dev/kvm + the kvm
# group) -- at `docker run` time.
#
# Requires: /dev/kvm on the host (KVM/nested-virt enabled), and the invoking
# user able to access it (see the --group-add below).
#
#   docker/run_android_emulator_tests.sh
set -euo pipefail

IMAGE=harpia-build
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -e /dev/kvm ]; then
    echo "docker/run_android_emulator_tests.sh: /dev/kvm not found -- this host" >&2
    echo "has no hardware virtualization available (or nested virt is disabled" >&2
    echo "up the host chain). The connectedAndroidTest run needs it; the" >&2
    echo "assembleDebugAndroidTest/assembleRelease compile-only checks (see" >&2
    echo "examples/android_consumer/README.md) don't." >&2
    exit 1
fi

KVM_GID="$(stat -c '%g' /dev/kvm)"

docker build -t "$IMAGE" "$REPO_ROOT"

# ANDROID_AVD_HOME is explicit (not just HOME=/tmp below) because the
# `emulator` binary resolves it directly -- but `avdmanager create avd`
# ignores ANDROID_AVD_HOME entirely and writes relative to Java's
# user.home, which getpwuid resolves to the image's baked-in /home/ubuntu
# regardless of HOME (same gotcha as Gradle's GRADLE_USER_HOME override
# above) -- hence also forcing user.home via JAVA_OPTS below.
docker run --rm -i \
    --device=/dev/kvm \
    --group-add "$KVM_GID" \
    -u "$(id -u):$(id -g)" \
    -v "$REPO_ROOT":/harpia \
    -v harpia-gradle-cache:/tmp/.gradle \
    -w /harpia \
    -e HOME=/tmp \
    -e GRADLE_USER_HOME=/tmp/.gradle \
    -e ANDROID_AVD_HOME=/tmp/.android/avd \
    -e JAVA_OPTS="-Duser.home=/tmp" \
    "$IMAGE" \
    bash /harpia/docker/_android_emulator_test_entrypoint.sh
