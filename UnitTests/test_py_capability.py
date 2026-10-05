"""python-target / py-versioning task 1: the shared capability ``Dispatcher``
(``harpia_runtime.capability.dispatch``), the gRPC handshake
(``harpia_runtime.capability.grpc.negotiate``) and the generated
``harpia_generated/capability/capabilities_<roothash>_grpc.py`` servicer.

- the advertised set equals the C++ ``capabilities_<roothash>_grpc.h`` list
  (``Capability.capability_common.message_type_names``);
- negotiate against a Python server returns that set; the generated
  ``GrpcServer`` registers the service (ungated, over its mTLS);
- a legacy peer (no capability service) and an unreachable / too-slow peer
  call the fallback exactly once and return ``None`` within the deadline;
- ``Dispatcher``: handler only when covered **and** registered, else the
  mandatory fallback;
- a C++ client (``harpia_capability.h`` ``negotiate``) against the Python
  server sees the same set [protoc + g++ + grpc++].
"""
import importlib
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests import test_py_rbac as R  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)
HASH = R.HASH
gen = R.gen
pki = R.pki


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


@pytest.fixture()
def use(gen):
    P.activate(P.py_root(gen))
    return gen


def _cap():
    return _mod("harpia_generated.capability.capabilities_{h}_grpc")


def _cpp_types(gen):
    header = open(os.path.join(gen, "generated", "cpp", "capability",
                               "capabilities_%s_grpc.h" % HASH)).read()
    block = header[header.index("kTypes = {"):header.index("};", header.index("kTypes = {"))]
    return re.findall(r'"([^"]+)"', block)


def test_advertised_set_matches_cpp(use):
    assert list(_cap().MESSAGE_TYPES) == _cpp_types(use)
    assert "users" in _cap().MESSAGE_TYPES


def _server(register=True, slow=0.0):
    import grpc
    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    if register:
        cap = _cap()
        if slow:
            class Slow(cap.capabilities_Service):
                def GetCapabilities(self, request, context):  # noqa: N802
                    time.sleep(slow)
                    return super().GetCapabilities(request, context)
            _mod("harpia_generated.protofiles.capabilities_service_pb2_grpc"
                 ).add_capabilities_ServiceServicer_to_server(Slow(), server)
        else:
            cap.add_to_server(server)
    else:  # some other service only: a pre-capability peer
        mod = _mod("harpia_generated.grpc.reception_desk_{h}_grpc")
        mod.add_to_server(mod.reception_desk_Service(None), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    return server, port


def _negotiate(port, timeout=2.0):
    import grpc
    calls = []
    ch = grpc.insecure_channel("127.0.0.1:%d" % port)
    try:
        t0 = time.monotonic()
        got = _mod("harpia_runtime.capability.grpc").negotiate(
            ch, timeout, on_legacy_peer=lambda: calls.append(1))
        return got, len(calls), time.monotonic() - t0
    finally:
        ch.close()


def test_negotiate(use):
    server, port = _server()
    try:
        got, legacy, _ = _negotiate(port)
    finally:
        server.stop(None).wait()
    assert got == set(_cpp_types(use)) and legacy == 0


def test_legacy_peer_calls_fallback_once(use):
    server, port = _server(register=False)
    try:
        got, legacy, _ = _negotiate(port)
    finally:
        server.stop(None).wait()
    assert got is None and legacy == 1


def test_timeout_is_honoured(use):
    server, port = _server(slow=3.0)
    try:
        got, legacy, took = _negotiate(port, timeout=0.3)
    finally:
        server.stop(0).wait()
    assert got is None and legacy == 1 and took < 2.0
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead = s.getsockname()[1]
    s.close()
    got, legacy, took = _negotiate(dead, timeout=0.5)
    assert got is None and legacy == 1 and took < 3.0


def test_generated_grpc_server_registers_it(use, pki, tmp_path):
    import grpc
    tls = _mod("harpia_runtime.tls")
    srv = _mod("harpia_generated.grpc.grpc_server_bringup").GrpcServer(
        R._grpc_pool(tmp_path), "localhost:0",
        mtls=tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]))
    srv.start()
    certless = grpc.ssl_channel_credentials(root_certificates=open(pki["ca"], "rb").read())
    ch = grpc.secure_channel("localhost:%d" % srv.port, certless)
    try:  # ungated: an anonymous caller gets the set
        got = _mod("harpia_runtime.capability.grpc").negotiate(ch, 5.0)
    finally:
        ch.close()
        srv.stop()
    assert got == set(_cpp_types(use))


def test_dispatcher(use):
    disp = _mod("harpia_runtime.capability.dispatch")
    with pytest.raises(TypeError):
        disp.Dispatcher()  # the fallback is mandatory
    seen = []
    d = disp.Dispatcher(lambda t: seen.append(("fallback", t)))
    d.on("users", lambda t: seen.append(("users", t)))
    d.dispatch("users", {"users", "data"})
    d.dispatch("users", {"data"})          # peer doesn't cover it
    d.dispatch("data", {"users", "data"})  # covered, no handler
    d.on("users", lambda t: seen.append(("users2", t)))
    d.dispatch("users", ["users"])
    assert seen == [("users", "users"), ("fallback", "users"), ("fallback", "data"),
                    ("users2", "users")]


_CPP = r'''
#include <chrono>
#include <cstdio>
#include <grpcpp/grpcpp.h>
#include "capability/harpia_capability.h"
int main(int, char** argv) {
    auto ch = ::grpc::CreateChannel(argv[1], ::grpc::InsecureChannelCredentials());
    int legacy = 0;
    auto types = harpia::capability::negotiate(ch, std::chrono::milliseconds(5000),
                                               [&] { ++legacy; });
    if (!types) { std::printf("LEGACY %d\n", legacy); return 0; }
    for (const auto& t : *types) std::printf("%s\n", t.c_str());
    return 0;
}
'''


def test_cpp_client_negotiates_with_python_server(use, tmp_path):
    cpp_root = os.path.join(use, "generated", "cpp")
    pf = os.path.join(cpp_root, "protofiles")
    srcs = [os.path.join(pf, f) for f in ("capabilities_service.pb.cc",
                                          "capabilities_service.grpc.pb.cc")]
    if shutil.which("g++") is None or not all(os.path.exists(s) for s in srcs):
        pytest.skip("needs g++ + the generated C++ gRPC stubs")
    (tmp_path / "c.cpp").write_text(_CPP)
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "grpc++", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "c"
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(tmp_path / "c.cpp"), *srcs,
                        "-o", str(exe), *flags, "-lpthread"],
                       capture_output=True, text=True, timeout=900)
    assert c.returncode == 0, c.stderr[-3000:]
    server, port = _server()
    try:
        out = subprocess.run([str(exe), "127.0.0.1:%d" % port], capture_output=True,
                             text=True, timeout=60).stdout.split()
    finally:
        server.stop(None).wait()
    assert out == sorted(_cpp_types(use))
    server, port = _server(register=False)
    try:
        out = subprocess.run([str(exe), "127.0.0.1:%d" % port], capture_output=True,
                             text=True, timeout=60).stdout.split()
    finally:
        server.stop(None).wait()
    assert out == ["LEGACY", "1"]


# -- task 2: HTTP + ZMQ slices ---------------------------------------------------------

def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http_server(register=True):
    router_mod = _mod("harpia_runtime.http.router")
    router = router_mod.Router()
    if register:
        _mod("harpia_generated.capability.capabilities_{h}_http").register_capabilities(
            router, "/api/v1")
    router.add("GET", "/api/v1/other", lambda req: router_mod.text(200, "x"))
    srv = router_mod.Server(router)
    srv.start()
    return srv


def _http_negotiate(port, timeout=2.0, base="/api/v1"):
    calls = []
    t0 = time.monotonic()
    got = _mod("harpia_runtime.capability.http").negotiate(
        "127.0.0.1", port, base, timeout, on_legacy_peer=lambda: calls.append(1))
    return got, len(calls), time.monotonic() - t0


def test_http_negotiate_and_body(use):
    import urllib.request
    srv = _http_server()
    try:
        got, legacy, _ = _http_negotiate(srv.port)
        with urllib.request.urlopen("http://127.0.0.1:%d/api/v1/capabilities" % srv.port) as r:
            body, ctype = r.read().decode(), r.headers["Content-Type"]
    finally:
        srv.stop()
    assert got == set(_cpp_types(use)) and legacy == 0
    assert ctype == "application/json"
    assert body == '{"messageTypes":[%s]}' % ",".join('"%s"' % t for t in _cpp_types(use))


def test_http_legacy_peers(use):
    import threading
    srv = _http_server(register=False)  # a pre-capability peer: 404
    try:
        assert _http_negotiate(srv.port)[:2] == (None, 1)
    finally:
        srv.stop()
    assert _http_negotiate(_free_port(), 1.0)[:2] == (None, 1)  # refused
    mute = socket.socket()  # accepts, never answers
    mute.bind(("127.0.0.1", 0))
    mute.listen(4)
    held = []
    threading.Thread(target=lambda: held.append(mute.accept()), daemon=True).start()
    try:
        got, legacy, took = _http_negotiate(mute.getsockname()[1], 0.4)
    finally:
        mute.close()
    assert (got, legacy) == (None, 1) and took < 2.0


def test_http_server_registers_route(use, pki, tmp_path):
    import ssl
    import urllib.request
    pool = R._grpc_pool(tmp_path)
    tls = _mod("harpia_runtime.tls")
    srv = _mod("harpia_generated.http.http_server_bringup").HttpServer(
        pool, host="localhost", rest_base="/v1",
        mtls=tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]))
    srv.start()
    try:
        ctx = ssl.create_default_context(cafile=pki["ca"])  # anonymous: ungated
        with urllib.request.urlopen("https://localhost:%d/v1/capabilities" % srv.port,
                                    context=ctx) as r:
            assert r.status == 200 and b'"messageTypes"' in r.read()
    finally:
        srv.stop()


def _zmq_responder(ctx, endpoint, n):
    import threading
    resp = _mod("harpia_generated.capability.capabilities_{h}_zmq").CapabilitiesResponder(
        ctx, endpoint)
    t = threading.Thread(target=lambda: [resp.serve_once() for _ in range(n)], daemon=True)
    t.start()
    return resp, t


def test_zmq_negotiate_and_legacy(use):
    zmq = pytest.importorskip("zmq")
    ctx = zmq.Context()
    port = _free_port()
    resp, t = _zmq_responder(ctx, "tcp://127.0.0.1:%d" % port, 1)
    calls = []
    neg = _mod("harpia_runtime.capability.zmq").negotiate
    try:
        got = neg(ctx, "tcp://127.0.0.1:%d" % port, 2.0, lambda: calls.append(1))
        t.join(5)
    finally:
        resp.close()
    assert got == set(_cpp_types(use)) and calls == []
    t0 = time.monotonic()
    assert neg(ctx, "tcp://127.0.0.1:%d" % _free_port(), 0.4, lambda: calls.append(1)) is None
    assert calls == [1] and time.monotonic() - t0 < 2.0
    ctx.term()


_CPP_PEER = r'''
#include <chrono>
#include <cstdio>
#include <iostream>
#include <string>
#include <thread>
#include "crow.h"
#include "capability/capabilities_@HASH@_http.h"
#include "capability/capabilities_@HASH@_zmq.h"
#include "capability/harpia_http_capability.h"
#include "capability/harpia_zmq_capability.h"
static void print(const std::optional<std::set<std::string>>& t, int legacy) {
    if (!t) { std::printf("LEGACY %d\n", legacy); return; }
    for (const auto& s : *t) std::printf("%s\n", s.c_str());
}
int main(int, char** argv) {
    const std::string mode = argv[1];
    int legacy = 0;
    if (mode == "http-client") {
        const auto t = harpia::capability::negotiate(argv[2], std::stoi(argv[3]), argv[4],
                                                     3000, [&] { ++legacy; });
        print(t, legacy);
    } else if (mode == "zmq-client") {
        ::zmq::context_t ctx;
        const auto t = harpia::capability::negotiate(
            ctx, argv[2], std::chrono::milliseconds(3000), [&] { ++legacy; });
        print(t, legacy);
    } else if (mode == "zmq-server") {
        ::zmq::context_t ctx;
        harpia::zmq_capability::capabilities_responder r(ctx, argv[2]);
        std::cout << "READY" << std::endl;
        r.serve_once();
    } else {  // http-server <port>
        crow::logger::setLogLevel(crow::LogLevel::Critical);
        crow::SimpleApp app;
        harpia::http_capability::register_capabilities(app, "/api/v1");
        app.bindaddr("127.0.0.1").port(std::stoi(argv[2]));
        std::thread t([&] { app.run(); });
        app.wait_for_server_start();
        std::cout << "READY" << std::endl;
        std::string line; std::getline(std::cin, line);
        app.stop(); t.join();
    }
    return 0;
}
'''


@pytest.fixture(scope="module")
def cap_peer(gen, tmp_path_factory):
    third = os.path.join(REPO_ROOT, "third_party")
    cpp_root = os.path.join(gen, "generated", "cpp")
    pb = os.path.join(cpp_root, "protofiles", "capabilities_service.pb.cc")
    if shutil.which("g++") is None or not os.path.exists(pb) or \
            not os.path.exists(os.path.join(third, "asio", "asio.hpp")):
        pytest.skip("needs g++ + protobuf + cppzmq + vendored crow/asio")
    d = tmp_path_factory.mktemp("cap_peer")
    (d / "p.cpp").write_text(_CPP_PEER.replace("@HASH@", HASH))
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf", "libzmq"],
                           capture_output=True, text=True, check=True).stdout.split()
    c = subprocess.run(["g++", "-std=c++17", "-DASIO_STANDALONE", "-I", cpp_root,
                        "-I", os.path.join(third, "crow"), "-I", os.path.join(third, "asio"),
                        str(d / "p.cpp"), pb, "-o", str(d / "p"), *flags, "-lpthread"],
                       capture_output=True, text=True, timeout=900)
    assert c.returncode == 0, c.stderr[-3000:]
    return str(d / "p")


def test_cpp_and_python_http_both_ways(use, cap_peer):
    want = sorted(_cpp_types(use))
    srv = _http_server()
    try:
        out = subprocess.run([cap_peer, "http-client", "127.0.0.1", str(srv.port), "/api/v1"],
                             capture_output=True, text=True, timeout=60).stdout.split()
        legacy = subprocess.run([cap_peer, "http-client", "127.0.0.1", str(srv.port), "/nope"],
                                capture_output=True, text=True, timeout=60).stdout.split()
    finally:
        srv.stop()
    assert out == want and legacy == ["LEGACY", "1"]
    port = _free_port()
    proc = subprocess.Popen([cap_peer, "http-server", str(port)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "READY"
        got, n, _ = _http_negotiate(port, 3.0)
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)
    assert got == set(want) and n == 0


def test_cpp_and_python_zmq_both_ways(use, cap_peer):
    zmq = pytest.importorskip("zmq")
    want = sorted(_cpp_types(use))
    ctx = zmq.Context()
    port = _free_port()
    resp, t = _zmq_responder(ctx, "tcp://127.0.0.1:%d" % port, 1)
    try:
        out = subprocess.run([cap_peer, "zmq-client", "tcp://127.0.0.1:%d" % port],
                             capture_output=True, text=True, timeout=60).stdout.split()
        t.join(5)
    finally:
        resp.close()
    assert out == want
    dead = subprocess.run([cap_peer, "zmq-client", "tcp://127.0.0.1:%d" % _free_port()],
                          capture_output=True, text=True, timeout=60).stdout.split()
    assert dead == ["LEGACY", "1"]
    port = _free_port()
    proc = subprocess.Popen([cap_peer, "zmq-server", "tcp://127.0.0.1:%d" % port],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "READY"
        got = _mod("harpia_runtime.capability.zmq").negotiate(
            ctx, "tcp://127.0.0.1:%d" % port, 3.0)
    finally:
        proc.wait(timeout=30)
        ctx.term()
    assert got == set(want)
