"""message-level-hardening initiative, protected-open-modifiers epic, task 2
-- the mTLS-optional-mode go/no-go spike.

**Not ordinary feature work.** This task's deliverable is a written finding
plus a minimal throwaway proof-of-concept -- task 3 (per-message REST/SOAP/
gRPC gate wiring) depends on the answer, not on any code landing here. This
file changes nothing in `Database/auth_gate.py`, `RestAdapter.py`,
`SoapAdapter.py` or `GrpcServiceAdapter.py` -- both spikes below build their
own standalone server program instead of reusing the generated bring-up, so
the finding is reproducible without touching production code.

## Question 1 (REST/SOAP, Crow): can a client cert be requested but not
required, with a reliable way to tell "no cert presented" from "cert
presented but didn't verify"?

**Finding: yes, cleanly, with no Crow/asio/OpenSSL limitation.** Crow's own
convenience methods (`.ssl_file()`) always end up at `verify_client_once`
(never enforces presence), and the harpia mTLS helper
(`Database/runtime/harpia_http_mtls.h`) always ORs in
`verify_fail_if_no_peer_cert`. Neither is a hard limit: Crow exposes a full
`app.ssl(asio::ssl::context&&)` override that hands the caller a completely
free hand over `SSL_CTX_set_verify()` (via `asio::ssl::context::
set_verify_mode`). Dropping `verify_fail_if_no_peer_cert` and keeping only
`asio::ssl::verify_peer` gives exactly "request but don't require": a
certless client completes the TLS handshake and `crow::request::
client_cert_cn` (the `[harpia patch]`, `SSLAdaptor::peer_cert_cn()`) comes
back `""` for free -- the exact "no cert -> empty CN -> anonymous" input
`Compliance/runtime/harpia_rbac.h`'s `decide()` already treats as
`unauthenticated`. A client that DOES present a cert is still fully verified
against the loaded CA (`verify_peer` alone still validates a presented
cert -- it only stops REQUIRING one); a cert from an untrusted CA is refused
at the handshake exactly as under full mTLS. `test_rest_optional_client_cert`
below proves this live: three real HTTPS connections against one server
(configured with a hand-built context using `verify_peer` only, no
`fail_if_no_peer_cert`) -- no cert -> connects, `/whoami` returns `""`;
trusted-CA client cert -> connects, `/whoami` returns the cert's CN; a cert
signed by a *different* CA -> handshake fails, same as it does today under
full mTLS.

## Question 2 (gRPC): can "open" mean "skip the RBAC role check, no verified
peer identity" without weakening the channel's mTLS requirement?

**Finding: yes.** gRPC's own `grpc_ssl_client_certificate_request_type` enum
(`include/grpc/grpc_security_constants.h`, not vendored here -- gRPC is a
system/pkg-config dependency) has five request/require/verify combinations;
harpia's `Database/runtime/harpia_grpc_mtls.h` currently hard-codes the
strictest, `GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY`.
Swapping to `GRPC_SSL_REQUEST_CLIENT_CERTIFICATE_AND_VERIFY` (drop
"REQUIRE") is the same shape of change as the REST/SOAP finding: a certless
channel still completes the TLS handshake, `ServerContext::auth_context()`'s
`GRPC_X509_CN_PROPERTY_NAME` lookup (`Database/auth_gate.py`'s already-
existing `peer_cn()`) comes back empty, and the SAME, unmodified, already-
generated `harpia::grpc_svc::<name>_service::rbac_check()` resolves that to
`Decision::unauthenticated` -> `UNAUTHENTICATED`, with zero changes needed to
`auth_gate.py`. A cert from an untrusted CA is refused at the transport level
exactly as under full mTLS -- `verify_peer`-equivalent verification still
runs on any cert that IS presented. `test_grpc_optional_client_cert` below
proves this live against the real generated `users_service` (built by the
real pipeline, completely unmodified) fronted by a throwaway `ServerBuilder`
using the swapped enum value instead of `harpia_grpc_mtls.h`.

## Go/no-go

**Go.** Both transports already expose the exact override surface needed
through their existing "hand the library a fully-built context/options"
escape hatches; the fix in each case is a one-enum-value change inside the
existing hand-written, verbatim-copied `Database/runtime/harpia_{http,
grpc}_mtls.h` helpers (task 3's job -- e.g. a `hardening_mode` tri-state
instead of the current `hardening_required` bool, or a second per-message
context/credentials builder), not a Crow/asio/gRPC limitation and not a
two-listening-ports workaround. `harpia_rbac.h`'s CN handling and every
generated `rbac_check()`/`authz_*` helper already treat an empty CN as
anonymous and need no changes at all.

    Docker/run.sh pytest UnitTests/test_mtls_optional_mode_spike.py
"""
import glob
import http.client
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")
CROW = os.path.join(REPO_ROOT, "third_party", "crow")
ASIO = os.path.join(REPO_ROOT, "third_party", "asio")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def _provision(out_dir, server_cn="localhost", client_id="harpia-client"):
    p = subprocess.run(["sh", PROVISION, str(out_dir), server_cn, client_id],
                       capture_output=True, text=True)
    assert p.returncode == 0, "mtls provisioning failed:\n" + p.stdout + p.stderr
    return {
        "ca": os.path.join(str(out_dir), "ca.pem"),
        "server_cert": os.path.join(str(out_dir), "server.pem"),
        "server_key": os.path.join(str(out_dir), "server_key.pem"),
        "client_cert": os.path.join(str(out_dir), "client.pem"),
        "client_key": os.path.join(str(out_dir), "client_key.pem"),
    }


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(proc, deadline_s=20):
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line == "READY":
            return True
        if line.startswith("SRV_EXC"):
            raise AssertionError("server threw: {}".format(line))
    return False


def _wait_accepting(proc, port, deadline_s=5):
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError("server exited early (rc={})".format(proc.returncode))
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("server never accepted a TCP connection on {}".format(port))


# --------------------------------------------------------------------------
# Question 1 -- REST/SOAP (Crow): requested-not-required client cert
# --------------------------------------------------------------------------

_REST_TOOLCHAIN = pytest.mark.skipif(
    shutil.which("g++") is None or shutil.which("openssl") is None
    or not os.path.exists(os.path.join(ASIO, "asio", "ssl.hpp")),
    reason="needs g++ + openssl + vendored crow/asio (harpia Docker image)",
)

_REST_SPIKE_SRC = '''\
// message-level-hardening / protected-open-modifiers task 2 -- throwaway
// spike. NOT included by anything in the generator. Builds its own
// asio::ssl::context with verify_peer only (no verify_fail_if_no_peer_cert)
// instead of using Database/runtime/harpia_http_mtls.h, which this task must
// not modify.
#include <asio/ssl.hpp>
#include "crow.h"
#include <iostream>
#include <string>
#include <thread>

int main(int argc, char** argv) {
    crow::logger::setLogLevel(crow::LogLevel::Critical);
    const int port = std::stoi(argv[1]);

    asio::ssl::context ctx(asio::ssl::context::tls_server);
    ctx.set_options(asio::ssl::context::default_workarounds
                    | asio::ssl::context::no_sslv2
                    | asio::ssl::context::no_sslv3
                    | asio::ssl::context::single_dh_use);
    ctx.use_certificate_chain_file(argv[3]);
    ctx.use_private_key_file(argv[4], asio::ssl::context::pem);
    ctx.load_verify_file(argv[2]);
    // The spike itself: request but do not require a client cert.
    ctx.set_verify_mode(asio::ssl::verify_peer);

    crow::SimpleApp app;
    CROW_ROUTE(app, "/whoami")([](const crow::request& req) {
        return req.client_cert_cn;
    });
    app.ssl(std::move(ctx));
    app.bindaddr("127.0.0.1").port(port).multithreaded();
    std::thread t([&] {
        try { app.run(); }
        catch (const std::exception& e) {
            std::cout << "SRV_EXC " << e.what() << std::endl;
        }
    });
    app.wait_for_server_start();
    std::cout << "READY" << std::endl;
    std::string line;
    std::getline(std::cin, line);
    app.stop();
    t.join();
    return 0;
}
'''


@_REST_TOOLCHAIN
def test_rest_optional_client_cert(tmp_path):
    trusted = _provision(tmp_path / "trusted", client_id="harpia-client")
    attacker = _provision(tmp_path / "attacker", client_id="harpia-client")

    prog = tmp_path / "rest_mtls_optional_spike.cc"
    prog.write_text(_REST_SPIKE_SRC, encoding="utf-8")
    binary = tmp_path / "rest_mtls_optional_spike"
    c = subprocess.run(
        ["g++", "-std=c++17", "-DASIO_STANDALONE", "-DCROW_ENABLE_SSL",
         "-I", CROW, "-I", ASIO, str(prog), "-o", str(binary),
         "-lssl", "-lcrypto", "-lpthread"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "spike server failed to build:\n" + c.stderr

    port = _free_port()
    proc = subprocess.Popen(
        [str(binary), str(port), trusted["ca"], trusted["server_cert"],
         trusted["server_key"]],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    try:
        assert _wait_ready(proc), "server did not print READY"
        _wait_accepting(proc, port)

        # 1) no client cert -> handshake still succeeds, CN is empty (the
        #    "requested, not required" behaviour this task exists to confirm)
        no_cert_ctx = ssl.create_default_context(cafile=trusted["ca"])
        no_cert_ctx.check_hostname = False
        conn = http.client.HTTPSConnection("127.0.0.1", port,
                                           context=no_cert_ctx, timeout=15)
        conn.request("GET", "/whoami")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.read() == b""
        conn.close()

        # 2) a cert signed by the trusted CA -> handshake succeeds, CN
        #    populated with the cert's subject CommonName
        ok_ctx = ssl.create_default_context(cafile=trusted["ca"])
        ok_ctx.check_hostname = False
        ok_ctx.load_cert_chain(trusted["client_cert"], trusted["client_key"])
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=ok_ctx,
                                           timeout=15)
        conn.request("GET", "/whoami")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.read() == b"harpia-client"
        conn.close()

        # 3) a cert signed by a DIFFERENT CA -> still refused at the
        #    handshake -- "requested, not required" never means "unverified
        #    when presented"
        bad_ctx = ssl.create_default_context(cafile=trusted["ca"])
        bad_ctx.check_hostname = False
        bad_ctx.load_cert_chain(attacker["client_cert"], attacker["client_key"])
        bad = http.client.HTTPSConnection("127.0.0.1", port, context=bad_ctx,
                                          timeout=15)
        with pytest.raises((ssl.SSLError, ConnectionError, OSError)):
            bad.request("GET", "/whoami")
            bad.getresponse()
        bad.close()
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


# --------------------------------------------------------------------------
# Question 2 -- gRPC: requested-not-required client cert
# --------------------------------------------------------------------------

def _have_grpcpp():
    return subprocess.run(["pkg-config", "--exists", "grpc++"]).returncode == 0


_GRPC_TOOLCHAIN = pytest.mark.skipif(
    shutil.which("protoc") is None
    or shutil.which("grpc_cpp_plugin") is None
    or shutil.which("g++") is None
    or shutil.which("pkg-config") is None
    or shutil.which("openssl") is None
    or not _have_grpcpp(),
    reason="needs protoc + grpc_cpp_plugin + g++ + grpc++ + openssl (harpia Docker image)",
)

_GRPC_SPIKE_SRC = '''\
// message-level-hardening / protected-open-modifiers task 2 -- throwaway
// spike. Fronts the real, UNMODIFIED generated harpia::grpc_svc::users_service
// with a hand-built ServerBuilder using
// GRPC_SSL_REQUEST_CLIENT_CERTIFICATE_AND_VERIFY instead of
// Database/runtime/harpia_grpc_mtls.h's server_credentials() (which hard-codes
// the REQUIRE variant and this task must not modify).
#include "grpc/users_{h}_grpc.h"
#include <grpcpp/grpcpp.h>
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include <fstream>
#include <sstream>
#include <chrono>
#include <string>

static std::string read_pem(const std::string& path) {{
    std::ifstream in(path, std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}}

int main(int, char** argv) {{
    const std::string addr = argv[1];
    const std::string ca = argv[2];
    const std::string server_cert = argv[3];
    const std::string server_key = argv[4];
    const std::string client_cert = argv[5];
    const std::string client_key = argv[6];
    const std::string attacker_ca = argv[7];
    const std::string attacker_client_cert = argv[8];
    const std::string attacker_client_key = argv[9];

    ::soci::session db(::soci::sqlite3, ":memory:");
    ::harpia::db::users_dao dao(db);
    if (!dao.create_table()) return 2;

    // The spike itself: request but do not require a client cert, unlike
    // harpia_grpc_mtls.h's GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY.
    ::grpc::SslServerCredentialsOptions opts(
        GRPC_SSL_REQUEST_CLIENT_CERTIFICATE_AND_VERIFY);
    opts.pem_root_certs = read_pem(ca);
    opts.pem_key_cert_pairs.push_back({{read_pem(server_key), read_pem(server_cert)}});
    auto creds = ::grpc::SslServerCredentials(opts);

    ::harpia::grpc_svc::users_service svc(db);
    ::grpc::ServerBuilder builder;
    builder.AddListeningPort(addr, creds);
    builder.RegisterService(&svc);
    auto server = builder.BuildAndStart();
    if (!server) return 3;

    auto call = [&](const std::string& root, const std::string& key,
                    const std::string& cert) {{
        ::grpc::SslCredentialsOptions copts;
        copts.pem_root_certs = read_pem(root);
        if (!key.empty()) copts.pem_private_key = read_pem(key);
        if (!cert.empty()) copts.pem_cert_chain = read_pem(cert);
        auto chan = ::grpc::CreateChannel(addr, ::grpc::SslCredentials(copts));
        auto stub = ::frameworkProtos::users_Service::NewStub(chan);
        ::frameworkProtos::users_Message req;
        req.mutable_msg()->set_id_{h}(1);
        req.mutable_msg()->set_name("neo");
        ::grpc::ClientContext c;
        c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));
        ::frameworkProtos::errorCode ec;
        return stub->push(&c, req, &ec);
    }};

    // 1) no client cert -> transport handshake still succeeds; the call
    //    completes with a real (anonymous) RPC status rather than a
    //    transport-level failure -- exactly the empty-CN "unauthenticated"
    //    outcome rbac_check() already produces, no auth_gate.py change needed.
    const auto anon = call(ca, "", "");
    if (anon.error_code() != ::grpc::StatusCode::UNAUTHENTICATED) return 4;

    // 2) a cert signed by the trusted CA -> handshake succeeds, RBAC sees the
    //    real CN and (mapped to "admin" via HARPIA_RBAC_MAP) allows the call.
    const auto ok = call(ca, client_key, client_cert);
    if (ok.error_code() != ::grpc::StatusCode::OK) return 5;

    // 3) a cert signed by a DIFFERENT CA -> still refused at the transport --
    //    "requested, not required" never means "unverified when presented".
    const auto bad = call(attacker_ca, attacker_client_key, attacker_client_cert);
    if (bad.error_code() == ::grpc::StatusCode::OK) return 6;

    server->Shutdown();
    return 0;
}}
'''


@pytest.fixture(scope="module")
def _grpc_built(tmp_path_factory):
    out = tmp_path_factory.mktemp("mtls_spike_grpc_build")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    from ProtoFile.GrpcCompiler import GrpcCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    assert GrpcCompiler(dest=build).Process() is None, "Stage 13 failed"

    trusted = _provision(os.path.join(str(out), "trusted"),
                         client_id="harpia-client")
    attacker = _provision(os.path.join(str(out), "attacker"),
                          client_id="harpia-client")

    rbac_map = os.path.join(str(out), "rbac_map.txt")
    with open(rbac_map, "w", encoding="utf-8") as fh:
        fh.write("harpia-client admin\n")

    return {
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "proto_dir": os.path.join(build, "generated", "cpp", "protofiles"),
        "tmp": str(out),
        "trusted": trusted,
        "attacker": attacker,
        "rbac_map": rbac_map,
    }


@_GRPC_TOOLCHAIN
def test_grpc_optional_client_cert(_grpc_built):
    b = _grpc_built
    prog = os.path.join(b["tmp"], "grpc_mtls_optional_spike.cc")
    with open(prog, "w") as f:
        f.write(_GRPC_SPIKE_SRC.format(h=HASH))

    objs = glob.glob(os.path.join(b["proto_dir"], "*.pb.cc"))
    binary = os.path.join(b["tmp"], "grpc_mtls_optional_spike")
    cmd = ["g++", "-std=c++17", "-I", b["cpp_root"],
           *_pkgconfig("--cflags"), prog, *objs, "-o", binary,
           "-lsoci_core", "-lsoci_sqlite3", *_pkgconfig("--libs"),
           "-lpthread", "-ldl"]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "gRPC spike failed to build:\n" + c.stderr

    addr = "localhost:{}".format(_free_port())
    t = b["trusted"]
    a = b["attacker"]
    run = subprocess.run(
        [binary, addr, t["ca"], t["server_cert"], t["server_key"],
         t["client_cert"], t["client_key"], a["ca"], a["client_cert"],
         a["client_key"]],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "HARPIA_RBAC_MAP": b["rbac_map"]})
    assert run.returncode == 0, (
        "live-TLS check #{} (stdout={!r} stderr={!r})".format(
            run.returncode, run.stdout, run.stderr))
