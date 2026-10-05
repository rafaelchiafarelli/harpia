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
