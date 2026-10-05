"""python-target / py-transports-http task 5: fail-safe mTLS
(``harpia_runtime.tls``) in the generated HTTP and gRPC bring-ups.

Generated under the repo's hardened profile; the fixture's ``protected`` /
``open`` messages make both bring-ups bake ``EMIT_TLS = True`` and
``CLIENT_CERT_REQUIRED = False`` (mixed mode), exactly like the C++
``kEmitTls`` / ``kClientCertRequired``. PKI from ``mtls_provision.sh``.

- fail-safe: no / partial / unreadable ``MtlsFiles`` → ``SecurityRefused``
  from ``HttpServer``, ``GrpcServer`` and every helper -- never plaintext;
- the baked constants equal the C++ bring-up's;
- required mode (HTTP and gRPC): certless client refused, CA-signed client
  accepted with its CN exposed to the handler, foreign-CA client refused;
- mixed mode: HTTP lets a certless client complete the handshake while a
  presented certificate is still verified (CN exposed, foreign CA refused);
  gRPC lets a certless client in and -- the documented Python limitation --
  never sees a client certificate;
- the generated ``HttpServer`` serves REST over TLS with the shared PKI.
C++ toolchains: a Python client calls the hardened C++ ``GrpcServer``, and a
C++ client calls the Python ``GrpcServer`` -- the same PKI both ways.
"""
import importlib
import os
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY or shutil.which("openssl") is None,
                                reason=P.SKIP_PY + " + openssl")

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")


def _provision(out_dir, client="harpia-client"):
    p = subprocess.run(["sh", PROVISION, str(out_dir), "localhost", client],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    d = str(out_dir)
    return {k: os.path.join(d, v) for k, v in (
        ("ca", "ca.pem"), ("cert", "server.pem"), ("key", "server_key.pem"),
        ("ccert", "client.pem"), ("ckey", "client_key.pem"))}


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_mtls"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    return _provision(tmp_path_factory.mktemp("pki"))


@pytest.fixture(scope="module")
def foreign(tmp_path_factory):
    return _provision(tmp_path_factory.mktemp("foreign_pki"))


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


def _tls():
    return _mod("harpia_runtime.tls")


def _server_files(p):
    return _tls().MtlsFiles(p["ca"], p["cert"], p["key"])


def _client_files(p, ca=None):
    return _tls().MtlsFiles(ca or p["ca"], p["ccert"], p["ckey"])


def _pool(tmp_path):
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "m.db"))
    with pool.borrow() as conn:
        _mod("harpia_generated.db.users_{h}_dao").users_dao(conn).create_table()
    return pool


def test_constants_match_cpp(gen):
    import re
    for kind, mod in (("http", "harpia_generated.http.http_server_bringup"),
                      ("grpc", "harpia_generated.grpc.grpc_server_bringup")):
        header = open(os.path.join(gen, "generated", "cpp", kind,
                                   kind + "_server_bringup.h")).read()
        want = {k: v == "true" for k, v in re.findall(
            r"inline constexpr bool k(\w+) = (true|false);", header)}
        m = _mod(mod)
        assert m.HARDENING_REQUIRED == want["HardeningRequired"]
        assert m.EMIT_TLS == want["EmitTls"]
        assert m.CLIENT_CERT_REQUIRED == want["ClientCertRequired"]


def test_fail_safe(gen, pki, tmp_path):
    tls = _tls()
    pool = _pool(tmp_path)
    for bad in (None, tls.MtlsFiles(), tls.MtlsFiles(pki["ca"], pki["cert"], ""),
                tls.MtlsFiles(pki["ca"], pki["cert"], str(tmp_path / "missing.pem"))):
        with pytest.raises(tls.SecurityRefused):
            _mod("harpia_generated.http.http_server_bringup").HttpServer(pool, mtls=bad)
        with pytest.raises(tls.SecurityRefused):
            _mod("harpia_generated.grpc.grpc_server_bringup").GrpcServer(pool, mtls=bad)
        with pytest.raises(tls.SecurityRefused):
            tls.http_server_context(True, bad)
        with pytest.raises(tls.SecurityRefused):
            tls.grpc_server_credentials(True, bad)
        with pytest.raises(tls.SecurityRefused):
            tls.grpc_channel_credentials(bad)
    assert tls.http_server_context(False, None) is None
    assert tls.grpc_server_credentials(False, None) is None


# -- HTTP ----------------------------------------------------------------------

def _cn_server(pki, required):
    router_mod, tls = _mod("harpia_runtime.http.router"), _tls()
    router = router_mod.Router()
    router.add("GET", "/whoami", lambda req: router_mod.text(
        200, tls.cn_from_peercert(req.peer.get("cert"))))
    srv = router_mod.Server(router, tls=tls.http_server_context(True, _server_files(pki),
                                                                 required))
    srv.start()
    return srv


def _https(port, ctx, path="/whoami", headers=None):
    req = urllib.request.Request("https://localhost:%d%s" % (port, path), headers=headers or {})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _certless(pki):
    return ssl.create_default_context(cafile=pki["ca"])


@pytest.mark.parametrize("required", [True, False])
def test_http_required_and_mixed(required, gen, pki, foreign):
    tls = _tls()
    srv = _cn_server(pki, required)
    try:
        assert _https(srv.port, tls.http_client_context(_client_files(pki))) == \
            (200, "harpia-client")
        bad = tls.http_client_context(_client_files(foreign, ca=pki["ca"]))
        with pytest.raises((urllib.error.URLError, ssl.SSLError, ConnectionError)):
            _https(srv.port, bad)
        if required:
            with pytest.raises((urllib.error.URLError, ssl.SSLError, ConnectionError)):
                _https(srv.port, _certless(pki))
        else:
            assert _https(srv.port, _certless(pki)) == (200, "")
    finally:
        srv.stop()


def test_generated_http_server_over_tls(gen, pki, tmp_path):
    tls = _tls()
    srv = _mod("harpia_generated.http.http_server_bringup").HttpServer(
        _pool(tmp_path), mtls=_server_files(pki))
    srv.start()
    try:
        status, _ = _https(srv.port, tls.http_client_context(_client_files(pki)), "/users")
        assert status in (200, 401, 403)  # served over mTLS; the gate is task 6's
        with pytest.raises((urllib.error.URLError, ConnectionError)):  # no plaintext
            urllib.request.urlopen("http://localhost:%d/users" % srv.port, timeout=5)
    finally:
        srv.stop()


# -- gRPC ----------------------------------------------------------------------

def _grpc_cn_server(pki, required):
    from concurrent.futures import ThreadPoolExecutor

    import grpc
    tls = _tls()
    handler = grpc.unary_unary_rpc_method_handler(
        lambda req, ctx: tls.grpc_peer_cn(ctx).encode(),
        request_deserializer=bytes, response_serializer=bytes)
    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        "harpia.Test", {"WhoAmI": handler}),))
    port = server.add_secure_port("localhost:0", tls.grpc_server_credentials(
        True, _server_files(pki), required))
    server.start()
    return server, port


def _whoami(port, creds):
    import grpc
    ch = grpc.secure_channel("localhost:%d" % port, creds)
    try:
        call = ch.unary_unary("/harpia.Test/WhoAmI", request_serializer=bytes,
                              response_deserializer=bytes)
        return call(b"", timeout=5).decode()
    finally:
        ch.close()


@pytest.mark.parametrize("required", [True, False])
def test_grpc_required_and_mixed(required, gen, pki, foreign):
    import grpc
    tls = _tls()
    server, port = _grpc_cn_server(pki, required)
    certless = grpc.ssl_channel_credentials(root_certificates=open(pki["ca"], "rb").read())
    try:
        good = _whoami(port, tls.grpc_channel_credentials(_client_files(pki)))
        if required:
            assert good == "harpia-client"
            for creds in (certless, tls.grpc_channel_credentials(
                    _client_files(foreign, ca=pki["ca"]))):
                with pytest.raises(grpc.RpcError) as e:
                    _whoami(port, creds)
                assert e.value.code() == grpc.StatusCode.UNAVAILABLE
        else:
            # documented limitation: Python gRPC mixed mode never requests a
            # client certificate, so every caller is anonymous (fail-closed)
            assert good == ""
            assert _whoami(port, certless) == ""
    finally:
        server.stop(None).wait()


# -- C++ <-> Python with one PKI --------------------------------------------------

def test_python_client_to_cpp_grpc_server(gen, tmp_path_factory):
    from UnitTests import _java_grpc_server_helpers as J
    if not J._have_grpcpp() or shutil.which("g++") is None:
        pytest.skip("needs the C++ gRPC toolchain")
    import grpc
    work = str(tmp_path_factory.mktemp("cpp_grpc_server"))
    server_bin = J.build_server(work)
    pki_dir = tmp_path_factory.mktemp("shared_pki")
    pki = _provision(pki_dir)
    svc = _mod("harpia_generated.protofiles.users_{h}_service_pb2")
    stub_mod = _mod("harpia_generated.protofiles.users_{h}_service_pb2_grpc")
    with J.running_server(server_bin, str(pki_dir), {}) as port:
        ch = grpc.secure_channel("localhost:%d" % port,
                                 _tls().grpc_channel_credentials(_client_files(pki)))
        try:
            hb = svc.users_HeartBeat()
            assert stub_mod.users_ServiceStub(ch).heartBeat(hb, timeout=10) == hb
        finally:
            ch.close()


_CPP_CLIENT = r'''
#include <cstdio>
#include <fstream>
#include <sstream>
#include <grpcpp/grpcpp.h>
#include "protofiles/users_%(h)s_service.grpc.pb.h"
static std::string pem(const char* p) { std::ifstream f(p); std::stringstream s; s << f.rdbuf(); return s.str(); }
int main(int, char** argv) {
    ::grpc::SslCredentialsOptions o;
    o.pem_root_certs = pem(argv[2]); o.pem_cert_chain = pem(argv[3]); o.pem_private_key = pem(argv[4]);
    auto stub = ::frameworkProtos::users_Service::NewStub(
        ::grpc::CreateChannel(argv[1], ::grpc::SslCredentials(o)));
    ::grpc::ClientContext c;
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(10));
    ::frameworkProtos::users_HeartBeat hb, out;
    std::printf("%%d\n", (int)stub->heartBeat(&c, hb, &out).error_code());
    return 0;
}
'''


def test_cpp_client_to_python_grpc_server(gen, pki, tmp_path):
    cpp_root = os.path.join(gen, "generated", "cpp")
    pf = os.path.join(cpp_root, "protofiles")
    srcs = [os.path.join(pf, f) for f in (
        "users_{}.pb.cc".format(HASH), "users_{}_service.pb.cc".format(HASH),
        "users_{}_service.grpc.pb.cc".format(HASH), "errorCode.pb.cc", "heartBeat.pb.cc")]
    if shutil.which("g++") is None or not all(os.path.exists(s) for s in srcs):
        pytest.skip("needs g++ + the generated C++ gRPC stubs")
    (tmp_path / "c.cpp").write_text(_CPP_CLIENT % {"h": HASH})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "grpc++", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "c"
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(tmp_path / "c.cpp"), *srcs,
                        "-o", str(exe), *flags, "-lpthread"],
                       capture_output=True, text=True, timeout=900)
    assert c.returncode == 0, c.stderr[-3000:]
    srv = _mod("harpia_generated.grpc.grpc_server_bringup").GrpcServer(
        _pool(tmp_path), "localhost:0", mtls=_server_files(pki))
    srv.start()
    try:
        out = subprocess.run([str(exe), "localhost:%d" % srv.port, pki["ca"], pki["ccert"],
                              pki["ckey"]], capture_output=True, text=True, timeout=60)
    finally:
        srv.stop()
    assert out.stdout.strip() == "0", out.stdout + out.stderr
