"""End-to-end demo test -- build the generated project with its own CMake and run
the ZMQ client/server, asserting a message actually crosses the wire.

This is the whole pipeline exercised as one: front-end -> proto -> (CMake)
protoc+grpc -> libprotofiles -> server/client linking the generated json + zmq
adapters -> a real message pushed from client to server over a ZMQ socket.

Skipped unless the full toolchain (cmake + protoc + grpc_cpp_plugin + g++ +
libzmq) is present, so the host suite stays green; runs fully in the harpia
Docker image:

    docker/run.sh pytest tests/test_demo.py
"""
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")


def _have_libzmq():
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None
        for t in ("cmake", "protoc", "grpc_cpp_plugin", "g++", "pkg-config"))
    or not _have_libzmq(),
    reason="needs cmake + protoc + grpc_cpp_plugin + g++ + libzmq (Docker image)",
)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """Generate the project, then build it with its own CMake."""
    out = tmp_path_factory.mktemp("harpia_demo")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    project = os.path.join(str(out), "build")
    cmbuild = os.path.join(str(out), "cmbuild")
    cfg = subprocess.run(["cmake", "-S", project, "-B", cmbuild],
                         capture_output=True, text=True, timeout=300)
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stderr + cfg.stdout
    bld = subprocess.run(["cmake", "--build", cmbuild, "-j", "4"],
                         capture_output=True, text=True, timeout=600)
    assert bld.returncode == 0, "cmake build failed:\n" + bld.stderr + bld.stdout
    return {
        "server": os.path.join(cmbuild, "server", "server"),
        "client": os.path.join(cmbuild, "client", "client"),
        "endpoint": "ipc://" + os.path.join(str(out), "demo.sock"),
    }


def test_demo_builds(demo):
    assert os.path.exists(demo["server"]), "server binary not built"
    assert os.path.exists(demo["client"]), "client binary not built"


def test_demo_message_crosses(demo):
    # server binds and waits for one message, then exits
    server = subprocess.Popen([demo["server"], demo["endpoint"]],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)
    try:
        time.sleep(0.5)  # let the receiver bind before the client connects
        client = subprocess.run([demo["client"], demo["endpoint"]],
                                capture_output=True, text=True, timeout=15)
        assert client.returncode == 0, "client failed:\n" + client.stdout + client.stderr

        out, _ = server.communicate(timeout=15)
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate()

    assert "received:" in out, "server never reported a message:\n" + out
    # the default sample sets the first scalar field; the value must survive
    assert "7" in out or "harpia-demo" in out, \
        "expected payload value missing from:\n" + out
