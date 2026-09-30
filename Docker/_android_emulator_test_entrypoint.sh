#!/usr/bin/env bash
# Runs INSIDE the harpia-build container (invoked by
# run_android_emulator_tests.sh, not meant to be run directly on the host):
# creates an AVD from the image's baked-in emulator + system image, boots it
# headless with KVM acceleration, generates+builds the Java-target project,
# and runs HarpiaTest/app_example/android_consumer's connectedAndroidTest suite
# against the running emulator. HardenedLinksAndroidTest (multi-system-reference
# / java-hardened-client task 4) also needs real hardened C++ servers: they are
# built and started here, in the background while the emulator boots, by
# UnitTests/run_android_hardened_servers.py -- the emulator reaches this
# container's loopback as 10.0.2.2.
set -euo pipefail

AVD_NAME=harpia_test_avd
SYSTEM_IMAGE="system-images;android-34;default;x86_64"
GEN_DIR=/tmp/gen
SERVERS_WORK=/tmp/hardened_work
SERVERS_ASSETS=/tmp/hardened_assets
SERVERS_LOG=/tmp/hardened_servers.log

echo "== Building + starting hardened C++ servers (background) =="
rm -rf "$SERVERS_WORK" "$SERVERS_ASSETS"
python3 UnitTests/run_android_hardened_servers.py "$SERVERS_WORK" "$SERVERS_ASSETS" \
    >"$SERVERS_LOG" 2>&1 &
SERVERS_PID=$!

echo "== Creating AVD $AVD_NAME =="
# -d picks a device profile so avdmanager doesn't prompt interactively for
# one -- piping "no" to that prompt was flaky under a non-TTY stdin (it
# sometimes read as EOF mid-prompt and errored instead of answering "no").
avdmanager create avd -n "$AVD_NAME" -k "$SYSTEM_IMAGE" -d "pixel_5" --force

echo "== Booting emulator headless =="
emulator -avd "$AVD_NAME" \
    -no-window -no-audio -no-boot-anim -no-snapshot \
    -gpu swiftshader_indirect -accel on -camera-back none -camera-front none \
    -logcat-output /tmp/emulator.log \
    >/tmp/emulator-stdout.log 2>&1 &
EMULATOR_PID=$!

cleanup() {
    kill "$EMULATOR_PID" 2>/dev/null || true
    kill -TERM "$SERVERS_PID" 2>/dev/null || true
    wait "$SERVERS_PID" 2>/dev/null || true
}
trap cleanup EXIT

check_emulator_alive() {
    if ! kill -0 "$EMULATOR_PID" 2>/dev/null; then
        echo "Emulator process (pid $EMULATOR_PID) exited unexpectedly" >&2
        echo "--- emulator-stdout.log ---" >&2
        cat /tmp/emulator-stdout.log >&2 || true
        exit 1
    fi
}

echo "== Waiting for device =="
BOOT_TIMEOUT=300
elapsed=0
until adb devices | grep -q "^emulator-"; do
    check_emulator_alive
    if [ "$elapsed" -ge "$BOOT_TIMEOUT" ]; then
        echo "No emulator device appeared within ${BOOT_TIMEOUT}s" >&2
        echo "--- emulator-stdout.log ---" >&2
        cat /tmp/emulator-stdout.log >&2 || true
        exit 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
done

echo "== Waiting for boot to complete =="
until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
    check_emulator_alive
    if [ "$elapsed" -ge "$BOOT_TIMEOUT" ]; then
        echo "Emulator did not finish booting within ${BOOT_TIMEOUT}s" >&2
        echo "--- emulator-stdout.log ---" >&2
        cat /tmp/emulator-stdout.log >&2 || true
        exit 1
    fi
    sleep 5
    elapsed=$((elapsed + 5))
done
adb shell input keyevent 82 || true
echo "== Emulator booted after ${elapsed}s =="

echo "== Generating Java-target project =="
rm -rf "$GEN_DIR"
HARPIA_GEN_LANG=java HARPIA_OUTPUT_DIR="$GEN_DIR" python3 main.py

echo "== Building generated project jar =="
(cd "$GEN_DIR/java" && gradle --no-daemon build)

echo "== Waiting for hardened servers =="
waited=0
until [ -f "$SERVERS_WORK/READY" ]; do
    if ! kill -0 "$SERVERS_PID" 2>/dev/null || [ "$waited" -ge 900 ]; then
        echo "hardened servers did not come up" >&2
        cat "$SERVERS_LOG" >&2 || true
        exit 1
    fi
    sleep 5
    waited=$((waited + 5))
done
grep SERVERS_READY "$SERVERS_LOG"

echo "== Running connectedAndroidTest =="
RESULTS=HarpiaTest/app_example/android_consumer/app/build/outputs/androidTest-results/connected
rm -rf "$RESULTS"
(cd HarpiaTest/app_example/android_consumer && gradle --no-daemon connectedAndroidTest \
    -PharpiaGenDir="$GEN_DIR" -PharpiaHardenedDir="$SERVERS_ASSETS")

echo "== Checking HardenedLinksAndroidTest actually ran (not skipped) =="
python3 - "$RESULTS" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
cases = [c for f in glob.glob(sys.argv[1] + "/**/*.xml", recursive=True)
         for c in ET.parse(f).getroot().iter("testcase")
         if c.get("classname", "").endswith("HardenedLinksAndroidTest")]
ran = [c.get("name") for c in cases if c.find("skipped") is None]
print("HardenedLinksAndroidTest ran:", ran)
sys.exit(0 if len(ran) == 2 and len(cases) == 2 else 1)
PY
