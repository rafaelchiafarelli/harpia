"""transport-authn epic, task 2 -- mTLS on the generated gRPC transport.

The gRPC path had no generated server bring-up (only per-message
harpia::grpc_svc::<name>_service impls; the consumer supplied their own
ServerBuilder). Task 2 adds one:

  grpc/harpia_grpc_mtls.h         hand-written credentials mechanism, copied
                                  verbatim (harpia::grpc_transport::{MtlsFiles,
                                  SecurityRefused, server_credentials,
                                  channel_credentials})
  grpc/grpc_server_bringup.h      rendered: #includes every <name>_grpc.h, bakes
                                  kHardeningRequired from
                                  transport_hardening_required(compliance), and
                                  defines harpia::grpc_transport::GrpcServer
  grpc/grpc_server_selection.json the F5 CryptoBackend choice + hardening flag

Two layers, same split as test_dds_security.py:
  - structural / pure Python (always): the files ship, the bring-up wires every
    service, the selection record + kHardeningRequired follow the compliance
    profile.
  - toolchain-gated (protoc + grpc_cpp_plugin + g++ + grpc++ + openssl, i.e.
    the harpia Docker image): harpia_grpc_mtls.h compiles and its fail-safe
    holds; and a live TLS gRPC call over a real socket is accepted with a
    client cert and refused without one.
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")
MTLS_SRC = os.path.join(REPO_ROOT, "Database", "runtime", "harpia_grpc_mtls.h")
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
def grpc_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_grpc_mtls")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "grpc")


def test_mtls_runtime_shipped_verbatim(grpc_dir):
    shipped = os.path.join(grpc_dir, "harpia_grpc_mtls.h")
    assert os.path.isfile(shipped)
    assert _read(shipped) == _read(MTLS_SRC)


def test_mtls_runtime_is_fail_safe():
    h = _read(MTLS_SRC)
    assert "class SecurityRefused" in h
    assert "GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY" in h
    # both directions refuse rather than silently downgrade
    assert h.count("throw SecurityRefused(") >= 2
    assert "InsecureServerCredentials()" in h and "InsecureChannelCredentials()" in h


def test_bringup_registers_every_service(grpc_dir):
    bringup = _read(os.path.join(grpc_dir, "grpc_server_bringup.h"))
    assert '#include "grpc/harpia_grpc_mtls.h"' in bringup
    assert "class GrpcServer" in bringup
    assert "inline constexpr bool kHardeningRequired = true;" in bringup  # repo profile is class_c

    services = sorted(
        os.path.basename(p)[: -len("_{}_grpc.h".format(HASH))]
        for p in glob.glob(os.path.join(grpc_dir, "*_{}_grpc.h".format(HASH))))
    assert services, "no per-message service headers collected"
    for name in services:
        assert '#include "grpc/{}_{}_grpc.h"'.format(name, HASH) in bringup
        assert "add< ::harpia::grpc_svc::{}_service>(db, builder);".format(name) in bringup


def test_selection_records_the_f5_choice(grpc_dir):
    sel = json.loads(_read(os.path.join(grpc_dir, "grpc_server_selection.json")))
    # repo project.harpia.yaml is class_c / cloud_connected -> fips backend,
    # hardened transport mandatory (same as dds_security_selection.json)
    assert sel == {
        "hardening_required": True,
        "crypto_backend": "openssl_fips",
        "cmake_package": "OpenSSL",
        "openssl_provider": "fips",
        "fips": True,
    }


def _drive(tmp_path, ctx, backend_name):
    from Database.GrpcServiceAdapter import GrpcServiceAdapter
    from Crypto.backend import get_backend

    class _Msg:
        name = "widget"
        md5Hash = "deadbeef"
        isEnum = False
        tableName = "widget_table"

    dest = str(tmp_path)
    GrpcServiceAdapter(messages=[_Msg()], dest=dest, compliance=ctx,
                       crypto_backend=get_backend(backend_name)).Process()
    return os.path.join(dest, "generated", "cpp", "grpc")


def test_hardening_flag_follows_compliance(tmp_path):
    """Low-risk profile + explicit standard backend: kHardeningRequired flips
    to false and the selection record with it."""
    from Compliance.context import (
        ComplianceContext, PhiHandling, RiskClass, Topology)
    ctx = ComplianceContext(risk_class=RiskClass.CLASS_A,
                            topology=Topology.STANDALONE,
                            phi_handling=PhiHandling.NONE, jurisdiction=[])
    out = _drive(tmp_path, ctx, "openssl")
    bringup = _read(os.path.join(out, "grpc_server_bringup.h"))
    assert "inline constexpr bool kHardeningRequired = false;" in bringup
    sel = json.loads(_read(os.path.join(out, "grpc_server_selection.json")))
    assert sel["hardening_required"] is False
    assert sel["crypto_backend"] == "openssl"
    assert sel["fips"] is False


def test_no_bringup_without_a_table_message(tmp_path):
    from Database.GrpcServiceAdapter import GrpcServiceAdapter

    class _Enum:
        name = "color"
        md5Hash = "deadbeef"
        isEnum = True
        tableName = None

    dest = str(tmp_path)
    GrpcServiceAdapter(messages=[_Enum()], dest=dest).Process()
    out = os.path.join(dest, "generated", "cpp", "grpc")
    assert not os.path.exists(os.path.join(out, "grpc_server_bringup.h"))
    assert not os.path.exists(os.path.join(out, "grpc_server_selection.json"))


# --------------------------------------------------------------------------
# toolchain-gated -- protoc + grpc_cpp_plugin + g++ + grpc++ + openssl
# --------------------------------------------------------------------------

def _have_grpcpp():
    return subprocess.run(["pkg-config", "--exists", "grpc++"]).returncode == 0


_toolchain = pytest.mark.skipif(
    shutil.which("protoc") is None
    or shutil.which("grpc_cpp_plugin") is None
    or shutil.which("g++") is None
    or shutil.which("pkg-config") is None
    or shutil.which("openssl") is None
    or not _have_grpcpp(),
    reason="needs protoc + grpc_cpp_plugin + g++ + grpc++ + openssl (harpia Docker image)",
)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_grpc_mtls_build")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    from ProtoFile.GrpcCompiler import GrpcCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    assert GrpcCompiler(dest=build).Process() is None, "Stage 13 failed"

    certs = os.path.join(str(out), "pki")
    p = subprocess.run(["sh", PROVISION, certs, "localhost"],
                       capture_output=True, text=True)
    assert p.returncode == 0, "mtls provisioning failed:\n" + p.stdout + p.stderr

    return {
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "proto_dir": os.path.join(build, "generated", "cpp", "protofiles"),
        "tmp": str(out),
        "ca": os.path.join(certs, "ca.pem"),
        "cert": os.path.join(certs, "client.pem"),
        "key": os.path.join(certs, "client_key.pem"),
        "server_cert": os.path.join(certs, "server.pem"),
        "server_key": os.path.join(certs, "server_key.pem"),
    }


@_toolchain
def test_mtls_helper_compiles_and_fail_safe_holds(built):
    """harpia_grpc_mtls.h is self-contained (only grpc++), returns insecure
    creds when hardening is off, and throws SecurityRefused when hardening is
    on but a PEM path is missing."""
    prog = os.path.join(built["tmp"], "mtls_helper.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "grpc/harpia_grpc_mtls.h"\n'
            "int main() {{\n"
            "    using namespace harpia::grpc_transport;\n"
            "    if (!server_credentials(false, {{}})) return 1;\n"
            "    if (!channel_credentials(false, {{}})) return 2;\n"
            "    try {{ server_credentials(true, {{}}); return 3; }}\n"
            "    catch (const SecurityRefused&) {{}}\n"
            "    try {{ channel_credentials(true, {{}}); return 4; }}\n"
            "    catch (const SecurityRefused&) {{}}\n"
            '    MtlsFiles f{{"{ca}", "{cert}", "{key}"}};\n'
            "    if (!server_credentials(true, f)) return 5;\n"
            "    if (!channel_credentials(true, f)) return 6;\n"
            "    return 0;\n"
            "}}\n".format(ca=built["ca"], cert=built["cert"], key=built["key"]))
    binary = os.path.join(built["tmp"], "mtls_helper")
    c = subprocess.run(["g++", "-std=c++17", "-I", built["cpp_root"],
                        *_pkgconfig("--cflags"), prog, "-o", binary,
                        *_pkgconfig("--libs"), "-lpthread", "-ldl"],
                       capture_output=True, text=True)
    assert c.returncode == 0, "mtls helper failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "fail-safe check #{}".format(run.returncode)


@_toolchain
def test_live_tls_roundtrip_requires_client_cert(built):
    """Stand up the generated GrpcServer over a real TCP socket with mTLS; a
    client presenting a task-1 client cert gets through, an insecure client is
    refused at the handshake."""
    proto = built["proto_dir"]
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    addr = "localhost:{}".format(port)

    prog = os.path.join(built["tmp"], "grpc_tls.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "grpc/grpc_server_bringup.h"\n'
            '#include "db/users_{h}_crudl.h"\n'
            "#include <grpcpp/grpcpp.h>\n"
            "#include <soci/soci.h>\n"
            "#include <soci/sqlite3/soci-sqlite3.h>\n"
            "#include <chrono>\n"
            "int main(int, char** argv) {{\n"
            "    const std::string addr = argv[1];\n"
            "    harpia::grpc_transport::MtlsFiles server_mtls{{argv[2], argv[3], argv[4]}};\n"
            "    harpia::grpc_transport::MtlsFiles client_mtls{{argv[2], argv[5], argv[6]}};\n"
            '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    harpia::grpc_transport::GrpcServer server(db, addr, server_mtls);\n"
            "    if (!server.ok()) return 3;\n"
            "    auto call = [&](std::shared_ptr< ::grpc::ChannelCredentials> creds) {{\n"
            "        auto chan = ::grpc::CreateChannel(addr, creds);\n"
            "        auto stub = ::frameworkProtos::users_Service::NewStub(chan);\n"
            "        ::frameworkProtos::users_Message req;\n"
            "        req.mutable_msg()->set_id_{h}(1);\n"
            '        req.mutable_msg()->set_name("neo");\n'
            "        ::grpc::ClientContext c;\n"
            '        c.AddMetadata("x-user", "users");\n'
            '        c.AddMetadata("x-pswd", "{h}");\n'
            "        c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));\n"
            "        ::frameworkProtos::errorCode ec;\n"
            "        return stub->push(&c, req, &ec).error_code();\n"
            "    }};\n"
            "    using namespace harpia::grpc_transport;\n"
            "    const auto ok = call(channel_credentials(true, client_mtls));\n"
            "    const auto bad = call(::grpc::InsecureChannelCredentials());\n"
            "    server.shutdown();\n"
            "    if (ok != ::grpc::StatusCode::OK) return 4;\n"
            "    if (bad == ::grpc::StatusCode::OK) return 5;\n"
            "    return 0;\n"
            "}}\n".format(h=HASH))

    # "*.pb.cc" already covers "*.grpc.pb.cc" -- globbing both double-links them
    objs = glob.glob(os.path.join(proto, "*.pb.cc"))
    binary = os.path.join(built["tmp"], "grpc_tls")
    cmd = ["g++", "-std=c++17", "-I", built["cpp_root"],
           *_pkgconfig("--cflags"), prog, *objs, "-o", binary,
           "-lsoci_core", "-lsoci_sqlite3", *_pkgconfig("--libs"),
           "-lpthread", "-ldl"]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "live-TLS program failed to build:\n" + c.stderr

    run = subprocess.run([binary, addr, built["ca"],
                          built["server_cert"], built["server_key"],
                          built["cert"], built["key"]],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, (
        "live-TLS check #{} (stdout={!r} stderr={!r})".format(
            run.returncode, run.stdout, run.stderr))
