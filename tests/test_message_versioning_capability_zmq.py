"""Integration tests for plans/message-versioning.md S5's ZMQ capability
handshake slice -- the REQ/REP capabilities_responder + negotiate() pair
(ZmqCapabilityAdapter). Complements test_message_versioning_capability.py
(gRPC slice); Dispatcher itself (now shared, capability/harpia_capability_
dispatch.h) is only tested once there, since it's transport-agnostic.

ZMQ has no existing metadata channel or session concept to piggyback the
handshake on (unlike gRPC call metadata or an HTTP request/response), so
this is its own small request/reply exchange reusing the same
capabilities_Request/capabilities_Response wire messages gRPC/HTTP already
defined.

Skipped unless protoc + g++ + pkg-config + libzmq + cppzmq (zmq.hpp) are
present, so the host suite stays green; runs fully in the harpia Docker
image:

    docker/run.sh pytest tests/test_message_versioning_capability_zmq.py
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")


def _have_libzmq():
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


pytestmark = pytest.mark.skipif(
    shutil.which("protoc") is None
    or shutil.which("g++") is None
    or shutil.which("pkg-config") is None
    or not _have_libzmq()
    or not os.path.exists("/usr/include/zmq.hpp"),
    reason="needs protoc + g++ + libzmq + cppzmq (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_zmq_capability")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from protoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "cpp_root": cpp_root,
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tmp": str(out),
    }


def _build_and_run(built, tmp_path, prog_text, name):
    prog = tmp_path / "{}.cc".format(name)
    prog.write_text(prog_text, encoding="utf-8")
    binary = str(tmp_path / name)
    cmd = ["g++", "-std=c++17", "-I", built["cpp_root"], *_pkgconfig("--cflags"),
           str(prog),
           os.path.join(built["proto_dir"], "capabilities_service.pb.cc"),
           "-o", binary, *_pkgconfig("--libs"), "-lpthread"]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return subprocess.run([binary], capture_output=True, text=True)


def test_responder_and_negotiate_real_roundtrip(built, tmp_path):
    r = _build_and_run(built, tmp_path, '''
#include "capability/capabilities_c96f8fd7f45108efee5a8ecb43eab1da_zmq.h"
#include "capability/harpia_zmq_capability.h"
#include <chrono>
#include <thread>
int main() {
    ::zmq::context_t ctx(1);
    harpia::zmq_capability::capabilities_responder responder(
        ctx, "inproc://harpia_capability_test");

    // inproc requires the bind to happen-before connect+send from the same
    // context, which the responder's constructor above already did; serve
    // exactly one request on a background thread while negotiate() runs.
    std::thread server([&]{ responder.serve_once(); });

    bool legacy_fired = false;
    auto types = harpia::capability::negotiate(
        ctx, "inproc://harpia_capability_test", std::chrono::milliseconds(2000),
        [&]{ legacy_fired = true; });
    server.join();

    if (legacy_fired) return 1;
    if (!types) return 2;
    if (types->count("users") == 0) return 3;   // a real message from the schema
    if (types->count("no_such_message") != 0) return 4;
    return 0;
}
''', "zmq_negotiate_ok")
    assert r.returncode == 0, "exit {}".format(r.returncode)


def test_negotiate_legacy_peer_is_a_named_outcome_not_a_hang(built, tmp_path):
    """No responder ever bound at the endpoint -- exactly the pre-feature
    legacy peer this plan calls for. Uses a real tcp:// port with nothing
    listening (not inproc://, whose connect-before-bind semantics vary by
    libzmq version) so this exercises the same async-connect-then-timeout
    path a real unreachable peer would hit. ZMQ's async connect means
    send() normally still succeeds (it just queues); the real signal is
    recv() timing out. Must resolve within the deadline, not hang."""
    r = _build_and_run(built, tmp_path, '''
#include "capability/harpia_zmq_capability.h"
#include <chrono>
int main() {
    ::zmq::context_t ctx(1);
    int legacy_fires = 0;
    // port with nothing bound to it -- reserved/unlikely-to-collide range
    auto types = harpia::capability::negotiate(
        ctx, "tcp://127.0.0.1:18199", std::chrono::milliseconds(500),
        [&]{ ++legacy_fires; });
    if (types) return 1;              // must be nullopt
    if (legacy_fires != 1) return 2;  // exactly once
    return 0;
}
''', "zmq_negotiate_legacy")
    assert r.returncode == 0, "exit {}".format(r.returncode)
