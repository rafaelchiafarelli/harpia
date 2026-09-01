"""End-to-end demo test -- build the generated project with its own CMake and run
the ZMQ client/server, asserting a message actually crosses the wire.

This is the whole pipeline exercised as one: front-end -> proto -> (CMake)
protoc+grpc -> libprotofiles -> server/client linking the generated json + zmq
adapters -> a real message pushed from client to server over a ZMQ socket.

Skipped unless the full toolchain (cmake + protoc + grpc_cpp_plugin + g++ +
libzmq) is present, so the host suite stays green; runs fully in the harpia
Docker image:

    Docker/run.sh pytest UnitTests/test_demo.py
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

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# pinned root-file hash (see UnitTests/CLAUDE.md) -- keys every generated
# filename; unchanged by editing an Include/ fixture.
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"


def _have_libzmq():
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


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


@pytest.fixture(scope="module")
def demo_curve(tmp_path_factory):
    """Same as `demo`, but configured with -DUSE_ZMQ_CURVE=ON -- the real
    build path a downstream consumer would use, not just the unit-level
    round-trip in test_stage13_zmq.py."""
    out = tmp_path_factory.mktemp("harpia_demo_curve")
    # transport-authn "zmq-zap-allowlist": under a hardened profile the
    # generated CURVE_SERVER sockets start a ZAP handler that denies every key
    # with no HARPIA_ZMQ_ALLOWLIST -- which would stall this encryption-only
    # CURVE demo. Pin a low-risk profile; the allowlist path is exercised by
    # test_zmq_zap.py.
    cfg_path = os.path.join(str(out), "low_risk.harpia.yaml")
    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write("risk_class: class_a\ntopology: standalone\n")
    env = {**os.environ, "HARPIA_COMPLIANCE_CONFIG": cfg_path}
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr

    project = os.path.join(str(out), "build")
    cmbuild = os.path.join(str(out), "cmbuild")
    cfg = subprocess.run(["cmake", "-S", project, "-B", cmbuild, "-DUSE_ZMQ_CURVE=ON"],
                         capture_output=True, text=True, timeout=300)
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stderr + cfg.stdout
    bld = subprocess.run(["cmake", "--build", cmbuild, "-j", "4"],
                         capture_output=True, text=True, timeout=600)
    assert bld.returncode == 0, "cmake build failed:\n" + bld.stderr + bld.stdout
    return {
        "server": os.path.join(cmbuild, "server", "server"),
        "client": os.path.join(cmbuild, "client", "client"),
        "endpoint": "ipc://" + os.path.join(str(out), "demo_curve.sock"),
        "proj": project,
        "cpp_root": os.path.join(project, "generated", "cpp"),
        "tmp": str(out),
    }


def test_demo_message_crosses_with_curve(demo_curve):
    """The generated demo, built with CURVE on, still delivers a real
    message end to end -- proves the ephemeral keypairs the keygen probe
    writes into harpia_zmq_curve_keys.h at configure time actually match
    between the server and client binaries produced by the same build."""
    server = subprocess.Popen([demo_curve["server"], demo_curve["endpoint"]],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True)
    try:
        time.sleep(0.5)
        client = subprocess.run([demo_curve["client"], demo_curve["endpoint"]],
                                capture_output=True, text=True, timeout=15)
        assert client.returncode == 0, "client failed:\n" + client.stdout + client.stderr
        assert "CURVE enabled" in client.stdout, \
            "client didn't report CURVE enabled:\n" + client.stdout

        out, _ = server.communicate(timeout=15)
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate()

    assert "CURVE enabled" in out, "server didn't report CURVE enabled:\n" + out
    assert "received:" in out, "server never reported a message:\n" + out
    assert "7" in out or "harpia-demo" in out, \
        "expected payload value missing from:\n" + out


def test_demo_stream_read_times_out(demo_curve):
    """zmq-lifecycle epic task 1, integration side: against the same
    CURVE-configured generated project the demo builds, a `stream` message's
    `<name>_stream` consumer connects to a bound-but-silent publisher and
    `read()` returns TIMEOUT -- promptly and without blocking -- rather than
    hanging waiting for data. Complements test_stage13_zmq.py's unit-level
    lifecycle coverage; does not re-run the CURVE round trip above."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=demo_curve["proj"]).Process() is None, \
        "Stage 7 (.pb.cc) generation failed"

    cpp_root = demo_curve["cpp_root"]
    adapter = os.path.join(cpp_root, "zmq", "sensor_feed_{}_zmq.h".format(HASH))
    assert os.path.exists(adapter), "sensor_feed stream transport missing"

    prog = os.path.join(demo_curve["tmp"], "demo_stream_timeout.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "zmq/sensor_feed_{h}_zmq.h"\n'
            "#include <chrono>\n"
            "namespace zt = harpia::zmq_transport;\n"
            "int main() {{\n"
            "    ::zmq::context_t ctx{{1}};\n"
            "    // a real publisher, bound but never publishing\n"
            '    zt::sensor_feed_publisher pub(ctx, "tcp://127.0.0.1:*");\n'
            "    std::string ep = pub.socket().get(::zmq::sockopt::last_endpoint);\n"
            "    zt::sensor_feed_stream s(ctx);\n"
            "    zt::StreamConfig c; c.endpoint = ep; c.read_timeout_ms = 200;\n"
            "    if (s.setup(c) != zt::StreamStatus::OK) return 1;\n"
            "    auto t0 = std::chrono::steady_clock::now();\n"
            "    auto r = s.read(200);\n"
            "    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(\n"
            "        std::chrono::steady_clock::now() - t0).count();\n"
            "    if (r.status != zt::StreamStatus::TIMEOUT) return 2;\n"
            "    if (r.msg.has_value()) return 3;\n"
            "    if (elapsed > 5000) return 4;   // timed, not blocked\n"
            "    if (s.stop() != zt::StreamStatus::STOPPED) return 5;\n"
            "    return 0;\n"
            "}}\n".format(h=HASH)
        )

    pb_cc = os.path.join(cpp_root, "protofiles",
                         "sensor_feed_{}.pb.cc".format(HASH))
    binary = os.path.join(demo_curve["tmp"], "demo_stream_timeout")
    cmd = ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
           prog, pb_cc, "-o", binary, *_pkgconfig("--libs")]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "stream timeout program failed to build:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, \
        "stream read timeout check failed at #{}".format(run.returncode)


def test_demo_stream_reclaims_dead_connection(demo_curve):
    """zmq-lifecycle epic task 2, integration side: against the same
    CURVE-configured generated project, a `stream` pointed at a dead endpoint
    (nothing bound -- the handshake never completes, no frame ever arrives)
    is reclaimed once `reclaim_after_ms` elapses: the next `read()` returns
    INVALID and stays there, and the object destructs without hanging. Uses a
    short `reclaim_after_ms` and the default long `stop_deadline_ms` so the
    dead-connection sweep, not task 1's watchdog, is what fires."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=demo_curve["proj"]).Process() is None, \
        "Stage 7 (.pb.cc) generation failed"

    cpp_root = demo_curve["cpp_root"]
    adapter = os.path.join(cpp_root, "zmq", "sensor_feed_{}_zmq.h".format(HASH))
    assert os.path.exists(adapter), "sensor_feed stream transport missing"

    prog = os.path.join(demo_curve["tmp"], "demo_stream_reclaim.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "zmq/sensor_feed_{h}_zmq.h"\n'
            "#include <unistd.h>\n"
            "namespace zt = harpia::zmq_transport;\n"
            "int main() {{\n"
            "    ::zmq::context_t ctx{{1}};\n"
            "    zt::sensor_feed_stream s(ctx);\n"
            "    zt::StreamConfig c;\n"
            '    c.endpoint = "tcp://127.0.0.1:5798";   // nothing bound here\n'
            "    c.read_timeout_ms = 10;\n"
            "    c.reclaim_after_ms = 150;\n"
            "    c.stop_deadline_ms = 30000;\n"
            "    if (s.setup(c) != zt::StreamStatus::OK) return 1;\n"
            "    if (s.read(10).status != zt::StreamStatus::TIMEOUT) return 2;\n"
            "    ::usleep(200000);   // past reclaim_after_ms\n"
            "    if (s.read(10).status != zt::StreamStatus::INVALID) return 3;\n"
            "    if (s.read(10).status != zt::StreamStatus::INVALID) return 4;\n"
            "    // scope exit: reclaimed stream must not hang on close\n"
            "    return 0;\n"
            "}}\n".format(h=HASH)
        )

    pb_cc = os.path.join(cpp_root, "protofiles",
                         "sensor_feed_{}.pb.cc".format(HASH))
    binary = os.path.join(demo_curve["tmp"], "demo_stream_reclaim")
    cmd = ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
           prog, pb_cc, "-o", binary, *_pkgconfig("--libs")]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "stream reclaim program failed to build:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, \
        "stream dead-connection reclamation check failed at #{}".format(
            run.returncode)
