"""dds-transport epic, task 2a -- the vendored DDS stack is real and builds.

Configures + builds `UnitTests/dds_spike/` (a throwaway Cyclone DDS + ddscxx
publisher/subscriber, see its CMakeLists.txt) against the Cyclone DDS the
Docker toolchain image installs from `third_party/cyclonedds{,-cxx}/`
(Docker/Dockerfile), then runs the binary and asserts one sample crossed a
publisher/subscriber pair under an explicit QoS profile.

Skipped unless cmake + g++ + a discoverable `CycloneDDS-CXX` CMake package
are present, so the bare-host suite stays green; runs fully in the image:

    Docker/run.sh pytest UnitTests/test_dds_vendor_spike.py
"""
import glob
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SPIKE_SRC = os.path.join(HERE, "dds_spike")


def _cyclonedds_cxx_findable():
    # find_package(CycloneDDS-CXX) resolves a *Config.cmake on CMAKE_PREFIX_PATH
    # or the standard prefixes; the Docker image installs to /usr/local.
    roots = ["/usr/local", "/usr", os.environ.get("CMAKE_PREFIX_PATH", "")]
    for root in filter(None, roots):
        for prefix in root.split(os.pathsep):
            if glob.glob(os.path.join(prefix, "lib*", "cmake", "CycloneDDS-CXX*",
                                     "CycloneDDS-CXX*.cmake")):
                return True
    return False


pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("cmake", "g++"))
    or not _cyclonedds_cxx_findable(),
    reason="needs cmake + g++ + an installed CycloneDDS-CXX (Docker image)",
)


def test_vendored_dds_pubsub_roundtrip(tmp_path):
    src = tmp_path / "dds_spike"
    shutil.copytree(SPIKE_SRC, src)
    build = tmp_path / "build"

    cfg = subprocess.run(
        ["cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"],
        capture_output=True, text=True,
    )
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stdout + cfg.stderr

    bld = subprocess.run(
        ["cmake", "--build", str(build), "-j", str(os.cpu_count() or 2)],
        capture_output=True, text=True,
    )
    assert bld.returncode == 0, "cmake build failed:\n" + bld.stdout + bld.stderr

    exe = build / "dds_pubsub_spike"
    assert exe.exists(), "spike binary not produced"

    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    out = run.stdout + run.stderr
    assert run.returncode == 0, "spike run failed:\n" + out

    # both QoS profiles construct and are accepted by a DataWriter
    assert "SPIKE reliable-profile reliability=RELIABLE history=KEEP_ALL" in out
    assert "SPIKE latest-profile reliability=BEST_EFFORT history=KEEP_LAST(1)" in out
    # the DDS-Security property API round-trips (task 3 supplies real values)
    assert "SPIKE security-hook props_staged=12 readback_ok=1" in out
    # and a real sample crossed the pub/sub pair
    assert "SPIKE roundtrip device_id=1 spo2=98 pulse_rate=72" in out
    assert out.strip().endswith("SPIKE OK")
