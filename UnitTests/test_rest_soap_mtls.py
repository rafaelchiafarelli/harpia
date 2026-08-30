"""transport-authn epic, task 3 -- mTLS on the generated REST + SOAP transport.

REST and SOAP had no generated server bring-up (only per-message
harpia::rest::register_<name> / harpia::soap::register_<name>_soap; the
consumer supplied their own crow::SimpleApp). Task 3 adds one -- REST and SOAP
share the app, so it is a single combined bring-up:

  http/harpia_http_mtls.h          hand-written mTLS context helper, copied
                                   verbatim (harpia::http_transport::{MtlsFiles,
                                   SecurityRefused, make_server_context} --
                                   builds an asio::ssl::context with
                                   verify_peer | verify_fail_if_no_peer_cert;
                                   crow's own ssl_file() only does
                                   verify_client_once, which lets a certless
                                   client through)
  http/http_server_bringup.h       rendered: #includes every <name>_rest.h +
                                   <name>_soap.h, registers every route on one
                                   crow::SimpleApp, bakes kHardeningRequired
                                   from transport_hardening_required(compliance)
  http/http_server_selection.json  the F5 CryptoBackend choice + hardening flag

Two layers, same split as test_grpc_mtls.py:
  - structural / pure Python (always): the files ship, the bring-up wires every
    route, the selection record + kHardeningRequired follow the compliance
    profile.
  - toolchain-gated (g++ + crow/asio/openssl + soci, i.e. the harpia Docker
    image): harpia_http_mtls.h compiles and its fail-safe holds; and a live
    HTTPS request against the generated HttpServer is served when the client
    presents a task-1 client cert and refused at the TLS handshake when it does
    not.
"""
import glob
import http.client
import json
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
MTLS_SRC = os.path.join(REPO_ROOT, "Database", "runtime", "harpia_http_mtls.h")
CROW = os.path.join(REPO_ROOT, "third_party", "crow")
ASIO = os.path.join(REPO_ROOT, "third_party", "asio")
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------
# structural -- pure Python, always runs
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def http_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_http_mtls")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "http")


def test_mtls_runtime_shipped_verbatim(http_dir):
    shipped = os.path.join(http_dir, "harpia_http_mtls.h")
    assert os.path.isfile(shipped)
    assert _read(shipped) == _read(MTLS_SRC)


def test_mtls_runtime_is_fail_safe():
    h = _read(MTLS_SRC)
    assert "class SecurityRefused" in h
    assert "verify_fail_if_no_peer_cert" in h
    assert "verify_peer" in h
    # incomplete files and the wrong-call-site case both refuse
    assert h.count("throw SecurityRefused(") >= 2


def test_bringup_registers_every_rest_and_soap_route(http_dir):
    bringup = _read(os.path.join(http_dir, "http_server_bringup.h"))
    assert "class HttpServer" in bringup
    assert "inline constexpr bool kHardeningRequired = true;" in bringup  # repo profile is class_c
    assert 'app_.ssl(make_server_context(kHardeningRequired, mtls));' in bringup
    assert "static_assert(!kHardeningRequired," in bringup  # no-SSL build fail-safe

    # every table message contributes a rest include, a soap include, and both
    # register calls -- derived from the collected rest headers, not hard-coded
    rest_hdrs = sorted(
        os.path.basename(p)[: -len("_{}_rest.h".format(HASH))]
        for p in glob.glob(os.path.join(os.path.dirname(http_dir), "rest",
                                        "*_{}_rest.h".format(HASH))))
    assert rest_hdrs, "no REST headers collected"
    for name in rest_hdrs:
        assert '#include "rest/{}_{}_rest.h"'.format(name, HASH) in bringup
        assert '#include "soap/{}_{}_soap.h"'.format(name, HASH) in bringup
        assert "::harpia::rest::register_{}(app_, db, rest_base);".format(name) in bringup
        assert "::harpia::soap::register_{}_soap(app_, db, soap_base);".format(name) in bringup


def test_selection_records_the_f5_choice(http_dir):
    sel = json.loads(_read(os.path.join(http_dir, "http_server_selection.json")))
    assert sel == {
        "hardening_required": True,
        "crypto_backend": "openssl_fips",
        "cmake_package": "OpenSSL",
        "openssl_provider": "fips",
        "fips": True,
    }


def test_hardening_flag_follows_compliance(tmp_path):
    from Database.RestAdapter import RestAdapter
    from Crypto.backend import get_backend
    from Compliance.context import (
        ComplianceContext, PhiHandling, RiskClass, Topology)

    class _Msg:
        name = "widget"
        md5Hash = "deadbeef"
        isEnum = False
        tableName = "widget_table"
        variables = []

    ctx = ComplianceContext(risk_class=RiskClass.CLASS_A,
                            topology=Topology.STANDALONE,
                            phi_handling=PhiHandling.NONE, jurisdiction=[])
    dest = str(tmp_path)
    RestAdapter(messages=[_Msg()], dest=dest, compliance=ctx,
                crypto_backend=get_backend("openssl")).Process()
    out = os.path.join(dest, "generated", "cpp", "http")
    bringup = _read(os.path.join(out, "http_server_bringup.h"))
    assert "inline constexpr bool kHardeningRequired = false;" in bringup
    sel = json.loads(_read(os.path.join(out, "http_server_selection.json")))
    assert sel["hardening_required"] is False
    assert sel["crypto_backend"] == "openssl"


def test_no_bringup_without_a_table_message(tmp_path):
    from Database.RestAdapter import RestAdapter

    class _Enum:
        name = "color"
        md5Hash = "deadbeef"
        isEnum = True
        tableName = None
        variables = []

    dest = str(tmp_path)
    RestAdapter(messages=[_Enum()], dest=dest).Process()
    out = os.path.join(dest, "generated", "cpp", "http")
    assert not os.path.exists(os.path.join(out, "http_server_bringup.h"))
    assert not os.path.exists(os.path.join(out, "http_server_selection.json"))


# --------------------------------------------------------------------------
# toolchain-gated -- g++ + crow/asio + openssl + soci
# --------------------------------------------------------------------------

def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


_toolchain = pytest.mark.skipif(
    shutil.which("protoc") is None
    or shutil.which("g++") is None
    or shutil.which("pkg-config") is None
    or shutil.which("openssl") is None
    or not os.path.exists(os.path.join(ASIO, "asio", "ssl.hpp")),
    reason="needs protoc + g++ + openssl + vendored crow/asio (harpia Docker image)",
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_http_mtls_build")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    certs = os.path.join(str(out), "pki")
    p = subprocess.run(["sh", PROVISION, certs, "localhost"],
                       capture_output=True, text=True)
    assert p.returncode == 0, "mtls provisioning failed:\n" + p.stdout + p.stderr

    return {
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "tmp": str(out),
        "ca": os.path.join(certs, "ca.pem"),
        "client_cert": os.path.join(certs, "client.pem"),
        "client_key": os.path.join(certs, "client_key.pem"),
        "server_cert": os.path.join(certs, "server.pem"),
        "server_key": os.path.join(certs, "server_key.pem"),
    }


@_toolchain
def test_mtls_helper_compiles_and_fail_safe_holds(built):
    prog = os.path.join(built["tmp"], "http_mtls_helper.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "http/harpia_http_mtls.h"\n'
            "int main() {{\n"
            "    using namespace harpia::http_transport;\n"
            "    try {{ make_server_context(false, {{}}); return 1; }}\n"
            "    catch (const SecurityRefused&) {{}}\n"
            "    try {{ make_server_context(true, {{}}); return 2; }}\n"
            "    catch (const SecurityRefused&) {{}}\n"
            '    MtlsFiles f{{"{ca}", "{cert}", "{key}"}};\n'
            "    auto ctx = make_server_context(true, f);\n"
            "    (void)ctx;\n"
            "    return 0;\n"
            "}}\n".format(ca=built["ca"], cert=built["server_cert"],
                          key=built["server_key"]))
    binary = os.path.join(built["tmp"], "http_mtls_helper")
    c = subprocess.run(
        ["g++", "-std=c++17", "-DASIO_STANDALONE", "-DCROW_ENABLE_SSL",
         "-I", built["cpp_root"], "-I", CROW, "-I", ASIO,
         prog, "-o", binary, "-lssl", "-lcrypto", "-lpthread"],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "http mtls helper failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "fail-safe check #{}".format(run.returncode)


@_toolchain
def test_live_https_requires_client_cert(built):
    """Stand up the generated HttpServer over real HTTPS; a request presenting a
    task-1 client cert is served (200 on the credentialed users list), a request
    with no client cert is refused at the TLS handshake."""
    cpp_root = built["cpp_root"]
    proto = os.path.join(cpp_root, "protofiles")

    prog = os.path.join(built["tmp"], "https_server.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "http/http_server_bringup.h"\n'
            '#include "db/users_{h}_crudl.h"\n'
            "#include <soci/soci.h>\n"
            "#include <soci/sqlite3/soci-sqlite3.h>\n"
            "#include <iostream>\n"
            "#include <string>\n"
            "#include <thread>\n"
            "int main(int, char** argv) {{\n"
            "    crow::logger::setLogLevel(crow::LogLevel::Critical);\n"
            "    const int port = std::stoi(argv[1]);\n"
            "    harpia::http_transport::MtlsFiles mtls{{argv[2], argv[3], argv[4]}};\n"
            '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            '    harpia::http_transport::HttpServer server(db, "/v1", "/soap", mtls);\n'
            '    server.app().bindaddr("127.0.0.1").port(port).multithreaded();\n'
            "    std::thread t([&]{{\n"
            "        try {{ server.app().run(); }}\n"
            "        catch (const std::exception& e) {{\n"
            '            std::cout << "SRV_EXC " << e.what() << std::endl; }}\n'
            "    }});\n"
            "    server.app().wait_for_server_start();\n"
            '    std::cout << "READY" << std::endl;\n'
            "    std::string line; std::getline(std::cin, line);\n"
            "    server.stop();\n"
            "    t.join();\n"
            "    return 0;\n"
            "}}\n".format(h=HASH))

    objs = glob.glob(os.path.join(proto, "*.pb.cc"))
    tinyxml = os.path.join(TINYXML2, "tinyxml2.cpp")
    binary = os.path.join(built["tmp"], "https_server")
    c = subprocess.run(
        ["g++", "-std=c++17", "-DASIO_STANDALONE", "-DCROW_ENABLE_SSL",
         "-I", cpp_root, "-I", CROW, "-I", ASIO, "-I", TINYXML2,
         *_pkgconfig("--cflags"), prog, *objs, tinyxml, "-o", binary,
         "-lsoci_core", "-lsoci_sqlite3", *_pkgconfig("--libs"),
         "-lssl", "-lcrypto", "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, "https server failed to build:\n" + c.stderr

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    proc = subprocess.Popen(
        [binary, str(port), built["ca"], built["server_cert"], built["server_key"]],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)

    def _die(msg):
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            rest = proc.stdout.read()
        except Exception:
            rest = ""
        proc.kill()
        raise AssertionError("{}\n--- server output ---\n{}".format(msg, rest))

    try:
        # crow logs to stdout; scan lines until our sentinel (or a server exc)
        deadline = time.time() + 20
        ready = False
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line == "READY":
                ready = True
                break
            if line.startswith("SRV_EXC"):
                _die("server threw: {}".format(line))
        if not ready:
            _die("server did not print READY")
        # give the (SSL) acceptor a moment past wait_for_server_start()
        for _ in range(50):
            if proc.poll() is not None:
                _die("server exited early (rc={})".format(proc.returncode))
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            _die("server never accepted a TCP connection on {}".format(port))

        # with a client cert -> served (200 on the credentialed list)
        ok_ctx = ssl.create_default_context(cafile=built["ca"])
        ok_ctx.check_hostname = False
        ok_ctx.load_cert_chain(built["client_cert"], built["client_key"])
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=ok_ctx,
                                           timeout=15)
        conn.request("GET", "/v1/users",
                     headers={"X-User": "users", "X-Pswd": HASH})
        resp = conn.getresponse()
        assert resp.status == 200, "credentialed mTLS GET got {}".format(resp.status)
        conn.close()

        # no client cert -> refused at the TLS handshake
        bad_ctx = ssl.create_default_context(cafile=built["ca"])
        bad_ctx.check_hostname = False
        bad = http.client.HTTPSConnection("127.0.0.1", port, context=bad_ctx,
                                          timeout=15)
        with pytest.raises((ssl.SSLError, ConnectionError, OSError)):
            bad.request("GET", "/v1/users",
                        headers={"X-User": "users", "X-Pswd": HASH})
            bad.getresponse()
        bad.close()
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
