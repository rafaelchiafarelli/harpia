"""dds-transport epic, task 2b -- the generated DDS transport builds and its
QoS mapping behaves as design-rules §4 specifies.

Mirrors test_demo.py's intent for DDS: run the real pipeline, then build the
generated per-message `dds/` headers + a driver against the Cyclone DDS the
Docker image installs, and run it. Under a simulated transient receiver gap
(subscriber stalls while the publisher keeps going):

  - `critical` alarm_event  (RELIABLE + KEEP_ALL)   -> every sample retained,
                                                       delivered in order
  - `dds` vitals_publication (BEST_EFFORT + KEEP_LAST(1)) -> burst collapses
                                                       to the newest sample

Skipped unless cmake + g++ + protoc + an installed CycloneDDS-CXX are
present, so the bare-host suite stays green; runs in the image:

    Docker/run.sh pytest UnitTests/test_dds_demo.py
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
DEMO_SRC = os.path.join(HERE, "dds_demo")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"


def _cyclonedds_cxx_findable():
    for root in ("/usr/local", "/usr", os.environ.get("CMAKE_PREFIX_PATH", "")):
        for prefix in filter(None, root.split(os.pathsep)):
            if glob.glob(os.path.join(prefix, "lib*", "cmake", "CycloneDDS-CXX*",
                                     "CycloneDDS-CXX*.cmake")):
                return True
    return False


pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("cmake", "g++", "protoc"))
    or not _cyclonedds_cxx_findable(),
    reason="needs cmake + g++ + protoc + installed CycloneDDS-CXX (Docker image)",
)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_dds_demo_gen")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    root = os.path.join(str(out), "build")
    gen_cpp = os.path.join(root, "generated", "cpp")
    # run_pipeline.py does the Python generation only -- protoc the two demo
    # messages' .proto text (build/proto/protofiles/) into gen_cpp/protofiles/
    # so the generated *_dds.h (and the driver) can `#include
    # "protofiles/<name>.pb.h"` off a single -I gen_cpp.
    protos = ["protofiles/{}_{}.proto".format(n, HASH)
              for n in ("alarm_event", "vitals_publication")]
    pc = subprocess.run(
        ["protoc", "--proto_path=" + os.path.join(root, "proto"),
         "--cpp_out=" + gen_cpp, *protos],
        capture_output=True, text=True,
    )
    assert pc.returncode == 0, "protoc failed:\n" + pc.stdout + pc.stderr
    return gen_cpp


def test_generated_dds_demo_qos_semantics(generated, tmp_path):
    src = tmp_path / "dds_demo"
    shutil.copytree(DEMO_SRC, src)
    # substitute the fixture hash into the driver's #include lines
    cpp_in = (src / "dds_demo.cpp.in").read_text()
    (src / "dds_demo.cpp").write_text(cpp_in.replace("@HASH@", HASH))
    (src / "dds_demo.cpp.in").unlink()

    build = tmp_path / "build"
    cfg = subprocess.run(
        ["cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
         "-DHARPIA_GEN=" + generated],
        capture_output=True, text=True,
    )
    assert cfg.returncode == 0, "configure failed:\n" + cfg.stdout + cfg.stderr

    bld = subprocess.run(
        ["cmake", "--build", str(build), "-j", str(os.cpu_count() or 2)],
        capture_output=True, text=True,
    )
    assert bld.returncode == 0, "build failed:\n" + bld.stdout + bld.stderr

    exe = build / "dds_demo"
    assert exe.exists()
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=90)
    out = run.stdout + run.stderr
    assert run.returncode == 0, "demo run failed:\n" + out
    assert "DDS_DEMO critical_received=20 order_ok=1 non_critical_received=" in out
    assert out.strip().endswith("DDS_DEMO OK")
