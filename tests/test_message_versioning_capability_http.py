"""Integration tests for plans/message-versioning.md S5's REST/SOAP
capability handshake slice -- the shared GET /capabilities route
(HttpCapabilityAdapter) + negotiate() over a real HTTP connection.
Complements test_message_versioning_capability.py (gRPC slice); Dispatcher
itself (now shared, capability/harpia_capability_dispatch.h) is only tested
once there, since it's transport-agnostic.

REST and SOAP share this one mechanism (both register routes on the same
crow::SimpleApp in a real deployment) rather than each getting its own --
see HttpCapabilityAdapter/CLAUDE.md.

Needs protoc + g++ + cc + pkg-config, same toolchain as test_stage12_rest.py
(compiles real Crow + asio + the raw-socket negotiate() client). Skipped
otherwise; runs in the harpia Docker image.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
CROW = os.path.join(REPO_ROOT, "third_party", "crow")
ASIO = os.path.join(REPO_ROOT, "third_party", "asio")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "g++", "cc", "pkg-config")),
    reason="needs protoc + g++ + cc + protobuf (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_capability_http")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from protoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    return {
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "tmp": str(out),
    }


def _build_and_run(built, tmp_path, prog_text, name):
    prog = tmp_path / "{}.cc".format(name)
    prog.write_text(prog_text, encoding="utf-8")
    binary = str(tmp_path / name)
    pb_cc = os.path.join(built["cpp_root"], "protofiles",
                         "capabilities_service.pb.cc")
    cmd = ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", CROW, "-I", ASIO,
           *_pkgconfig("--cflags"), str(prog), pb_cc, "-o", binary,
           *_pkgconfig("--libs"), "-lpthread"]
    c = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return subprocess.run([binary], capture_output=True, text=True, timeout=30)


def test_capabilities_route_and_negotiate_real_roundtrip(built, tmp_path):
    r = _build_and_run(built, tmp_path, '''
#include "capability/capabilities_{h}_http.h"
#include "capability/harpia_http_capability.h"
#include <chrono>
#include <thread>
int main() {{
    crow::SimpleApp app;
    app.loglevel(crow::LogLevel::Warning);
    harpia::http_capability::register_capabilities(app, "/api/v1");
    const int port = 18101;
    auto fut = app.bindaddr("127.0.0.1").port(port).multithreaded().run_async();
    app.wait_for_server_start();

    bool legacy_fired = false;
    auto types = harpia::capability::negotiate(
        "127.0.0.1", port, "/api/v1", 2000, [&]{{ legacy_fired = true; }});

    app.stop(); fut.get();

    if (legacy_fired) return 1;
    if (!types) return 2;
    if (types->count("users") == 0) return 3;   // a real message from the schema
    if (types->count("no_such_message") != 0) return 4;
    return 0;
}}
'''.format(h=HASH), "http_negotiate_ok")
    assert r.returncode == 0, "exit {}".format(r.returncode)


def test_negotiate_legacy_peer_is_a_named_outcome_not_a_hang(built, tmp_path):
    """A real Crow server that has OTHER routes but never registered
    /capabilities (a genuine pre-feature legacy peer) -- 404, resolved to
    the named legacy-peer outcome, not an error and not a hang."""
    r = _build_and_run(built, tmp_path, '''
#include "capability/harpia_http_capability.h"
#include "crow.h"
int main() {
    crow::SimpleApp app;
    app.loglevel(crow::LogLevel::Warning);
    app.route_dynamic("/api/v1/ping").methods(crow::HTTPMethod::GET)(
        [](const crow::request&, crow::response& res) {
            res.body = "pong"; res.end();
        });
    const int port = 18102;
    auto fut = app.bindaddr("127.0.0.1").port(port).multithreaded().run_async();
    app.wait_for_server_start();

    int legacy_fires = 0;
    auto types = harpia::capability::negotiate(
        "127.0.0.1", port, "/api/v1", 2000, [&]{ ++legacy_fires; });

    app.stop(); fut.get();

    if (types) return 1;              // must be nullopt
    if (legacy_fires != 1) return 2;  // exactly once
    return 0;
}
''', "http_negotiate_legacy")
    assert r.returncode == 0, "exit {}".format(r.returncode)


def test_negotiate_unreachable_host_is_a_named_outcome_not_a_hang(built, tmp_path):
    """Nothing listening at all (connection refused) -- also resolves to
    the legacy-peer outcome, not a hang, well within the timeout."""
    r = _build_and_run(built, tmp_path, '''
#include "capability/harpia_http_capability.h"
int main() {
    int legacy_fires = 0;
    auto types = harpia::capability::negotiate(
        "127.0.0.1", 18103, "/api/v1", 1000, [&]{ ++legacy_fires; });
    if (types) return 1;
    if (legacy_fires != 1) return 2;
    return 0;
}
''', "http_negotiate_unreachable")
    assert r.returncode == 0, "exit {}".format(r.returncode)
