"""message-level-hardening initiative, protected-open-modifiers epic, task 4
-- mixed-mode proof: one project, both gated and open messages, all three
transports, driven end to end against a live generated server (not just a
unit-level check of the generated source text -- that's task 3's own test,
UnitTests/test_message_hardening_gate.py).

Two fixtures, both living in HarpiaTest/Include/file3.harpia (not
test.harpia -- see LexicalAnalizer/CLAUDE.md on why fixtures land in an
Include file: only the root file's md5 tags messages, so this never perturbs
the pinned HASH constants elsewhere in UnitTests/):

  - `reception_desk` (`open`): HarpiaTest/test.harpia's own compliance
    profile (project.harpia.yaml: class_c / cloud_connected) is hardened.
    `open` routes it to the FLAT X-User/X-Pswd-style credential gate
    regardless of the project default (`Database/auth_gate.effective_rbac()`
    -- `open` does NOT mean "no credential check at all", it means "never
    the RBAC/client-cert check"), so a caller with no client CERTIFICATE
    but the right flat credential is served; `users` -- a plain message in
    the very same project -- keeps demanding a real client-cert identity
    (the RBAC gate) exactly as before this epic, and ignores the flat
    credential entirely.
  - `vault` (`protected`): under HarpiaTest/test.harpia's own hardened
    profile, `protected` is a documented no-op (redundant with the
    project-wide default -- see UnitTests/test_message_hardening_gate.py for
    that case). The interesting half needs the OPPOSITE profile, so this
    module drives the same test.harpia + Include/file3.harpia schema again
    under a low-risk override (`HARPIA_COMPLIANCE_CONFIG`, the same
    technique test_stage11_soap.py/test_stage12_rest.py/test_stage13.py
    already use to exercise the flat-gate variant) where
    `transport_hardening_required()` is False. There, `vault` still forces
    a real client-cert identity (401 / UNAUTHENTICATED with none) --
    `Database/auth_gate.transport_mode()`'s project-wide promotion is what
    makes that possible at all in an otherwise-plaintext project -- while
    `users` stays on the unchanged flat credential, now simply carried over
    the TLS connection the promotion turned on project-wide (Crow serves one
    crow::SimpleApp over one listening socket, so once ANY message needs
    TLS the whole app speaks HTTPS; the flat credential CHECK itself is
    transport-agnostic and doesn't change).

Toolchain-gated (protoc + grpc_cpp_plugin + g++ + pkg-config + openssl +
vendored crow/asio, i.e. the harpia Docker image); skipped on a bare host.
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
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_toolchain = pytest.mark.skipif(
    any(shutil.which(t) is None
        for t in ("protoc", "grpc_cpp_plugin", "g++", "pkg-config"))
    or shutil.which("openssl") is None
    or not os.path.exists(os.path.join(ASIO, "asio", "ssl.hpp")),
    reason="needs protoc + grpc_cpp_plugin + g++ + pkg-config + openssl + "
          "vendored crow/asio (harpia Docker image)",
)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"],
                        capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _build(tmp_path_factory, name, low_risk):
    """Runs the real pipeline against HarpiaTest/test.harpia (+ Include/
    file3.harpia's reception_desk/vault fixtures), optionally under a
    low-risk compliance override, then Stage 7 + Stage 13 codegen."""
    out = tmp_path_factory.mktemp(name)
    env = dict(os.environ)
    if low_risk:
        cfg = os.path.join(str(out), "low_risk.harpia.yaml")
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write("risk_class: class_a\ntopology: standalone\n")
        env["HARPIA_COMPLIANCE_CONFIG"] = cfg
    r = subprocess.run([sys.executable, RUNNER, str(out)], cwd=REPO_ROOT,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    from ProtoFile.GrpcCompiler import GrpcCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    assert GrpcCompiler(dest=build).Process() is None, "Stage 13 failed"

    certs = os.path.join(str(out), "pki")
    p = subprocess.run(["sh", PROVISION, certs, "localhost", "mixed-client"],
                       capture_output=True, text=True)
    assert p.returncode == 0, "mtls provisioning failed:\n" + p.stdout + p.stderr

    rbac_map = os.path.join(str(out), "rbac_map.txt")
    with open(rbac_map, "w", encoding="utf-8") as fh:
        fh.write("mixed-client admin\n")

    return {
        "tmp": str(out),
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "proto_dir": os.path.join(build, "generated", "cpp", "protofiles"),
        "ca": os.path.join(certs, "ca.pem"),
        "server_cert": os.path.join(certs, "server.pem"),
        "server_key": os.path.join(certs, "server_key.pem"),
        "client_cert": os.path.join(certs, "client_mixed-client.pem"),
        "client_key": os.path.join(certs, "client_mixed-client_key.pem"),
        "rbac_map": rbac_map,
    }


@pytest.fixture(scope="module")
def hardened(tmp_path_factory):
    """HarpiaTest's own project.harpia.yaml profile (class_c/cloud_connected,
    hardened) -- `reception_desk` (`open`) is the interesting message here;
    `vault` (`protected`) is a documented no-op under this profile."""
    return _build(tmp_path_factory, "mixed_hardened", low_risk=False)


@pytest.fixture(scope="module")
def open_profile(tmp_path_factory):
    """A low-risk override (class_a/standalone) -- `vault` (`protected`) is
    the interesting message here; `reception_desk` (`open`) is a no-op."""
    return _build(tmp_path_factory, "mixed_open", low_risk=True)


def _client_ctx(ca, cert=None, key=None):
    ctx = ssl.create_default_context(cafile=ca)
    ctx.check_hostname = False
    if cert:
        ctx.load_cert_chain(cert, key)
    return ctx


def _wait_ready(proc, deadline_s=20):
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            raise AssertionError("server exited before READY:\n" +
                                 proc.stdout.read())
        if line.strip() == "READY":
            return
        if line.startswith("SRV_EXC"):
            raise AssertionError("server threw: " + line)
    raise AssertionError("server did not print READY")


def _wait_accepting(proc, port, deadline_s=10):
    for _ in range(deadline_s * 5):
        if proc.poll() is not None:
            raise AssertionError("server exited early (rc={})".format(
                proc.returncode))
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.2)
    raise AssertionError("server never accepted a connection on {}".format(port))


def _stop(proc):
    try:
        proc.stdin.close()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


# --------------------------------------------------------------------------
# REST + SOAP -- one crow::SimpleApp, same pattern as test_rbac.py /
# test_rest_soap_mtls.py
# --------------------------------------------------------------------------

_HTTP_SERVER_CC = '''\
#include "http/http_server_bringup.h"
#include "db/reception_desk_{h}_crudl.h"
#include "db/vault_{h}_crudl.h"
#include "db/users_{h}_crudl.h"
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include <iostream>
#include <string>
#include <thread>
int main(int, char** argv) {{
    crow::logger::setLogLevel(crow::LogLevel::Critical);
    const int port = std::stoi(argv[1]);
    harpia::http_transport::MtlsFiles mtls{{argv[2], argv[3], argv[4]}};
    ::soci::session db(::soci::sqlite3, ":memory:");
    harpia::db::reception_desk_dao rdao(db);
    harpia::db::vault_dao vdao(db);
    harpia::db::users_dao udao(db);
    if (!rdao.create_table() || !vdao.create_table() || !udao.create_table())
        return 2;
    ::reception_desk r1; r1.set_id_{h}(1); r1.set_visitor_name("ada");
    if (!rdao.create(r1)) return 3;
    ::vault v1; v1.set_id_{h}(1); v1.set_secret_code("hunter2");
    if (!vdao.create(v1)) return 4;
    ::users u1; u1.set_id_{h}(1); u1.set_name("neo");
    if (!udao.create(u1)) return 5;
    harpia::http_transport::HttpServer server(db, "/v1", "/soap", mtls);
    server.app().bindaddr("127.0.0.1").port(port).multithreaded();
    std::thread t([&]{{
        try {{ server.app().run(); }}
        catch (const std::exception& e) {{
            std::cout << "SRV_EXC " << e.what() << std::endl;
        }}
    }});
    server.app().wait_for_server_start();
    std::cout << "READY" << std::endl;
    std::string line; std::getline(std::cin, line);
    server.stop();
    t.join();
    return 0;
}}
'''


def _build_http_server(g, tmp):
    prog = os.path.join(tmp, "mixed_http_server.cc")
    with open(prog, "w") as f:
        f.write(_HTTP_SERVER_CC.format(h=HASH))
    objs = glob.glob(os.path.join(g["proto_dir"], "*.pb.cc"))
    binary = os.path.join(tmp, "mixed_http_server")
    c = subprocess.run(
        ["g++", "-std=c++17", "-DASIO_STANDALONE", "-DCROW_ENABLE_SSL",
         "-I", g["cpp_root"], "-I", CROW, "-I", ASIO, "-I", TINYXML2,
         *_pkgconfig("--cflags"), prog, *objs,
         os.path.join(TINYXML2, "tinyxml2.cpp"), "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3", *_pkgconfig("--libs"),
         "-lssl", "-lcrypto", "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, "mixed http server failed to build:\n" + c.stderr
    return binary


def _start_http_server(binary, ca, server_cert, server_key, rbac_map):
    port = _free_port()
    proc = subprocess.Popen(
        [binary, str(port), ca, server_cert, server_key],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env={**os.environ, "HARPIA_RBAC_MAP": rbac_map})
    _wait_ready(proc)
    _wait_accepting(proc, port)
    return proc, port


def _http_get(port, ctx, path, headers=None):
    conn = http.client.HTTPSConnection("127.0.0.1", port, context=ctx,
                                       timeout=15)
    conn.request("GET", path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


_SOAP_ENV_OPEN = ('<soap:Envelope xmlns:soap='
                  '"http://schemas.xmlsoap.org/soap/envelope/">')


def _soap_get_body(id_, name=None, pswd=None):
    header = ""
    if name is not None:
        header = ("<soap:Header><credentials><user>{}</user>"
                  "<pswd>{}</pswd></credentials></soap:Header>").format(
                  name, pswd)
    return (_SOAP_ENV_OPEN + header +
           "<soap:Body><get><id>{}</id></get></soap:Body></soap:Envelope>"
           .format(id_))


def _soap_call(port, ctx, path, xml):
    conn = http.client.HTTPSConnection("127.0.0.1", port, context=ctx,
                                       timeout=15)
    conn.request("POST", path, body=xml, headers={"Content-Type": "text/xml"})
    resp = conn.getresponse()
    out = (resp.status, resp.read().decode("utf-8", "replace"))
    conn.close()
    return out


@_toolchain
def test_open_message_served_anonymously_over_rest_and_soap(hardened, tmp_path):
    g = hardened
    binary = _build_http_server(g, str(tmp_path))
    proc, port = _start_http_server(binary, g["ca"], g["server_cert"],
                                    g["server_key"], g["rbac_map"])
    try:
        anon_ctx = _client_ctx(g["ca"])
        admin_ctx = _client_ctx(g["ca"], g["client_cert"], g["client_key"])
        flat_ok = {"X-User": "reception_desk", "X-Pswd": HASH}

        # `open`: no client CERTIFICATE needed -- the flat credential alone
        # (never the RBAC/client-cert axis) serves the request.
        st, body = _http_get(port, anon_ctx, "/v1/reception_desk", flat_ok)
        assert st == 200 and b"ada" in body, (st, body)
        st, body = _http_get(port, anon_ctx, "/v1/reception_desk/1", flat_ok)
        assert st == 200 and b"ada" in body, (st, body)
        # still a real gate -- no credential at all is refused.
        st, _ = _http_get(port, anon_ctx, "/v1/reception_desk")
        assert st == 401

        # a plain message in the SAME project still demands a client-cert
        # identity, and ignores the flat credential entirely.
        st, _ = _http_get(port, anon_ctx, "/v1/users")
        assert st == 401
        st, _ = _http_get(port, anon_ctx, "/v1/users",
                          {"X-User": "users", "X-Pswd": HASH})
        assert st == 401
        st, _ = _http_get(port, admin_ctx, "/v1/users")
        assert st == 200

        # SOAP rides the same crow::SimpleApp.
        st, txt = _soap_call(port, anon_ctx, "/soap/reception_desk",
                            _soap_get_body(1, "reception_desk", HASH))
        assert st == 200 and "getResponse" in txt, (st, txt)
        st, txt = _soap_call(port, anon_ctx, "/soap/reception_desk",
                            _soap_get_body(1))
        assert st == 401 and "Fault" in txt, (st, txt)
        st, txt = _soap_call(port, anon_ctx, "/soap/users", _soap_get_body(1))
        assert st == 401 and "Fault" in txt, (st, txt)
        st, txt = _soap_call(port, admin_ctx, "/soap/users", _soap_get_body(1))
        assert st == 200 and "getResponse" in txt, (st, txt)
    finally:
        _stop(proc)


@_toolchain
def test_protected_message_refuses_anonymous_under_open_profile_rest_and_soap(
        open_profile, tmp_path):
    g = open_profile
    binary = _build_http_server(g, str(tmp_path))
    proc, port = _start_http_server(binary, g["ca"], g["server_cert"],
                                    g["server_key"], g["rbac_map"])
    try:
        anon_ctx = _client_ctx(g["ca"])
        admin_ctx = _client_ctx(g["ca"], g["client_cert"], g["client_key"])

        # `vault` forces this otherwise-plaintext project's transport to
        # TLS (client cert requested, not required) -- an anonymous TLS
        # connection (no cert) is still refused by vault's own RBAC gate.
        st, _ = _http_get(port, anon_ctx, "/v1/vault")
        assert st == 401
        st, _ = _http_get(port, admin_ctx, "/v1/vault")
        assert st == 200

        # `users` stays on the unchanged flat X-User/X-Pswd credential --
        # still no client cert needed, just now carried over the TLS
        # connection the vault promotion turned on project-wide (one
        # crow::SimpleApp, one listening socket).
        st, _ = _http_get(port, anon_ctx, "/v1/users",
                          {"X-User": "users", "X-Pswd": HASH})
        assert st == 200
        st, _ = _http_get(port, anon_ctx, "/v1/users")  # no credential at all
        assert st == 401

        st, txt = _soap_call(port, anon_ctx, "/soap/vault", _soap_get_body(1))
        assert st == 401 and "Fault" in txt, (st, txt)
        st, txt = _soap_call(port, admin_ctx, "/soap/vault", _soap_get_body(1))
        assert st == 200 and "getResponse" in txt, (st, txt)
        st, txt = _soap_call(port, anon_ctx, "/soap/users",
                            _soap_get_body(1, "users", HASH))
        assert st == 200 and "getResponse" in txt, (st, txt)
    finally:
        _stop(proc)


# --------------------------------------------------------------------------
# gRPC -- same pattern as test_grpc_mtls.py / test_rbac.py
# --------------------------------------------------------------------------

_GRPC_COMMON_CC = '''\
#include "grpc/grpc_server_bringup.h"
#include "db/reception_desk_{h}_crudl.h"
#include "db/vault_{h}_crudl.h"
#include "db/users_{h}_crudl.h"
#include <grpcpp/grpcpp.h>
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include <chrono>
#include <fstream>
#include <sstream>
#include <string>
using namespace harpia::grpc_transport;
static std::string read_pem(const std::string& path) {{
    std::ifstream in(path, std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}}
static ::grpc::StatusCode push_reception_desk(
        ::frameworkProtos::reception_desk_Service::Stub* stub,
        bool with_flat_credential) {{
    ::frameworkProtos::reception_desk_Message req;
    req.mutable_msg()->set_id_{h}(2);
    req.mutable_msg()->set_visitor_name("grace");
    ::grpc::ClientContext c;
    if (with_flat_credential) {{
        c.AddMetadata("x-user", "reception_desk");
        c.AddMetadata("x-pswd", "{h}");
    }}
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));
    ::frameworkProtos::errorCode ec;
    return stub->push(&c, req, &ec).error_code();
}}
static ::grpc::StatusCode push_vault(
        ::frameworkProtos::vault_Service::Stub* stub) {{
    ::frameworkProtos::vault_Message req;
    req.mutable_msg()->set_id_{h}(2);
    req.mutable_msg()->set_secret_code("swordfish");
    ::grpc::ClientContext c;
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));
    ::frameworkProtos::errorCode ec;
    return stub->push(&c, req, &ec).error_code();
}}
static ::grpc::StatusCode push_users(
        ::frameworkProtos::users_Service::Stub* stub,
        bool with_flat_credential) {{
    ::frameworkProtos::users_Message req;
    req.mutable_msg()->set_id_{h}(2);
    req.mutable_msg()->set_name("trin");
    ::grpc::ClientContext c;
    if (with_flat_credential) {{
        c.AddMetadata("x-user", "users");
        c.AddMetadata("x-pswd", "{h}");
    }}
    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));
    ::frameworkProtos::errorCode ec;
    return stub->push(&c, req, &ec).error_code();
}}
// harpia::grpc_transport::channel_credentials() always requires a complete
// client identity (MtlsFiles.complete()) -- there is deliberately no
// "anonymous client" mode in that helper, since a real deployment's client
// always presents its own identity. Task 2's "requested, not required"
// finding is about the SERVER accepting a certless caller, so testing it
// needs a channel built directly with only a root cert -- no
// pem_private_key/pem_cert_chain -- exactly like the task 2 spike
// (test_mtls_optional_mode_spike.py) did.
static std::shared_ptr<::grpc::Channel> anon_channel(
        const std::string& addr, const std::string& ca) {{
    ::grpc::SslCredentialsOptions opts;
    opts.pem_root_certs = read_pem(ca);
    return ::grpc::CreateChannel(addr, ::grpc::SslCredentials(opts));
}}
static std::shared_ptr<::grpc::Channel> admin_channel(
        const std::string& addr, const std::string& ca,
        const std::string& ccrt, const std::string& ckey) {{
    return ::grpc::CreateChannel(
        addr, channel_credentials(true, MtlsFiles{{ca, ccrt, ckey}}));
}}
'''

# `reception_desk` (`open`): the flat credential alone serves it, no client
# cert, regardless of the project's own hardening default; `users` (plain,
# hardened default) demands a real client-cert identity and ignores the flat
# credential entirely.
_GRPC_HARDENED_MAIN = '''\
int main(int, char** argv) {{
    const std::string addr = argv[1];
    const std::string ca = argv[2], scrt = argv[3], skey = argv[4];
    const std::string ccrt = argv[5], ckey = argv[6];
    MtlsFiles server_mtls{{ca, scrt, skey}};
    ::soci::session db(::soci::sqlite3, ":memory:");
    harpia::db::reception_desk_dao rdao(db);
    harpia::db::vault_dao vdao(db);
    harpia::db::users_dao udao(db);
    if (!rdao.create_table() || !vdao.create_table() || !udao.create_table())
        return 2;
    GrpcServer server(db, addr, server_mtls);
    if (!server.ok()) return 3;
    auto anon = anon_channel(addr, ca);
    auto admin = admin_channel(addr, ca, ccrt, ckey);
    int rc = 0;
    {{
        auto stub = ::frameworkProtos::reception_desk_Service::NewStub(anon);
        if (push_reception_desk(stub.get(), true) != ::grpc::StatusCode::OK) rc = 10;
        if (push_reception_desk(stub.get(), false) != ::grpc::StatusCode::UNAUTHENTICATED)
            rc = 11;
    }}
    {{
        auto stub = ::frameworkProtos::users_Service::NewStub(anon);
        if (push_users(stub.get(), false) != ::grpc::StatusCode::UNAUTHENTICATED)
            rc = 12;
        if (push_users(stub.get(), true) != ::grpc::StatusCode::UNAUTHENTICATED)
            rc = 13;  // flat metadata ignored -- this route is RBAC, not flat.
    }}
    {{
        auto stub = ::frameworkProtos::users_Service::NewStub(admin);
        if (push_users(stub.get(), false) != ::grpc::StatusCode::OK) rc = 14;
    }}
    server.shutdown();
    return rc;
}}
'''

# `vault` (`protected`) still forces a real client-cert identity even though
# this project's own default is unhardened; `users` (plain, unhardened
# default) stays on the flat credential, ignoring client-cert identity.
_GRPC_OPEN_PROFILE_MAIN = '''\
int main(int, char** argv) {{
    const std::string addr = argv[1];
    const std::string ca = argv[2], scrt = argv[3], skey = argv[4];
    const std::string ccrt = argv[5], ckey = argv[6];
    MtlsFiles server_mtls{{ca, scrt, skey}};
    ::soci::session db(::soci::sqlite3, ":memory:");
    harpia::db::reception_desk_dao rdao(db);
    harpia::db::vault_dao vdao(db);
    harpia::db::users_dao udao(db);
    if (!rdao.create_table() || !vdao.create_table() || !udao.create_table())
        return 2;
    GrpcServer server(db, addr, server_mtls);
    if (!server.ok()) return 3;
    auto anon = anon_channel(addr, ca);
    auto admin = admin_channel(addr, ca, ccrt, ckey);
    int rc = 0;
    {{
        auto stub = ::frameworkProtos::vault_Service::NewStub(anon);
        if (push_vault(stub.get()) != ::grpc::StatusCode::UNAUTHENTICATED) rc = 10;
    }}
    {{
        auto stub = ::frameworkProtos::vault_Service::NewStub(admin);
        if (push_vault(stub.get()) != ::grpc::StatusCode::OK) rc = 11;
    }}
    {{
        auto stub = ::frameworkProtos::users_Service::NewStub(anon);
        if (push_users(stub.get(), true) != ::grpc::StatusCode::OK) rc = 12;
        if (push_users(stub.get(), false) != ::grpc::StatusCode::UNAUTHENTICATED)
            rc = 13;
    }}
    server.shutdown();
    return rc;
}}
'''


def _run_grpc_mixed_check(g, tmp, main_src):
    prog = os.path.join(tmp, "mixed_grpc.cc")
    with open(prog, "w") as f:
        f.write((_GRPC_COMMON_CC + main_src).format(h=HASH))
    objs = glob.glob(os.path.join(g["proto_dir"], "*.pb.cc"))
    binary = os.path.join(tmp, "mixed_grpc")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", g["cpp_root"], *_pkgconfig("--cflags"),
         prog, *objs, "-o", binary, "-lsoci_core", "-lsoci_sqlite3",
         *_pkgconfig("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, "mixed grpc driver failed to build:\n" + c.stderr

    addr = "localhost:{}".format(_free_port())
    run = subprocess.run(
        [binary, addr, g["ca"], g["server_cert"], g["server_key"],
         g["client_cert"], g["client_key"]],
        capture_output=True, text=True, timeout=90,
        env={**os.environ, "HARPIA_RBAC_MAP": g["rbac_map"]})
    assert run.returncode == 0, "mixed grpc check #{} (stdout={!r} stderr={!r})".format(
        run.returncode, run.stdout, run.stderr)


@_toolchain
def test_open_message_served_anonymously_over_grpc(hardened, tmp_path):
    _run_grpc_mixed_check(hardened, str(tmp_path), _GRPC_HARDENED_MAIN)


@_toolchain
def test_protected_message_refuses_anonymous_over_grpc_under_open_profile(
        open_profile, tmp_path):
    _run_grpc_mixed_check(open_profile, str(tmp_path), _GRPC_OPEN_PROFILE_MAIN)
