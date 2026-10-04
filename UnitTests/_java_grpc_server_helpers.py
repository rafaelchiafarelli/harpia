"""Shared harness for the Java-client-vs-C++-server gRPC tests
(multi-system-reference / java-hardened-client: test_java_grpc_mtls.py,
test_java_session_client.py, and later tasks). Not itself a test module.

Builds the generated **C++** `GrpcServer` (hardened, HarpiaTest fixture) into a
standalone server binary, provisions a dev PKI, and starts/stops the server as
a subprocess that serves until its stdin closes. The Java side is built with
`_java_gradle_helpers.build_and_classpath`.
"""
import contextlib
import glob
import os
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import wait_for_listening  # noqa: E402


def _have_grpcpp():
    return (shutil.which("pkg-config") is not None
            and subprocess.run(["pkg-config", "--exists", "grpc++"]).returncode == 0)


HAS_TOOLCHAIN = (
    shutil.which("protoc") is not None
    and shutil.which("grpc_cpp_plugin") is not None
    and shutil.which("g++") is not None
    and shutil.which("openssl") is not None
    and _have_grpcpp()
    and shutil.which("gradle") is not None
    and shutil.which("java") is not None
)
SKIP_REASON = ("needs protoc + grpc_cpp_plugin + g++ + grpc++ + openssl AND "
               "gradle+JDK (harpia Docker image)")


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


_SERVER_CC = """\
#include "grpc/grpc_server_bringup.h"
#include "db/users_{h}_crudl.h"
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include <iostream>
#include <string>
// argv: addr ca server_cert server_key. Serves until stdin closes.
int main(int, char** argv) {{
    harpia::grpc_transport::MtlsFiles mtls{{argv[2], argv[3], argv[4]}};
    ::soci::session db(::soci::sqlite3, ":memory:");
    harpia::db::users_dao dao(db);
    if (!dao.create_table()) return 2;
    harpia::grpc_transport::GrpcServer server(db, argv[1], mtls);
    if (!server.ok()) return 3;
    std::cout << "LISTENING" << std::endl;
    std::string line;
    while (std::getline(std::cin, line)) {{}}
    server.shutdown();
    return 0;
}}
"""


def build_server(tmp):
    """Generate the HarpiaTest fixture (C++), compile its protos + gRPC stubs,
    and link a standalone hardened GrpcServer binary. Returns its path."""
    r = subprocess.run([sys.executable, RUNNER, tmp], cwd=REPO_ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    from ProtoFile.ProtoCompiler import ProtoCompiler
    from ProtoFile.GrpcCompiler import GrpcCompiler
    build = os.path.join(tmp, "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    assert GrpcCompiler(dest=build).Process() is None, "Stage 13 failed"
    cpp_root = os.path.join(build, "generated", "cpp")

    server_cc = os.path.join(tmp, "server.cc")
    with open(server_cc, "w") as f:
        f.write(_SERVER_CC.format(h=HASH))
    server_bin = os.path.join(tmp, "server")
    objs = glob.glob(os.path.join(cpp_root, "protofiles", "*.pb.cc"))
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
                        server_cc, *objs, "-o", server_bin,
                        "-lsoci_core", "-lsoci_sqlite3", *_pkgconfig("--libs"),
                        "-lpthread", "-ldl"],
                       capture_output=True, text=True)
    assert c.returncode == 0, "server failed to build:\n" + c.stderr
    return server_bin


def provision(out_dir, *identities):
    """mtls_provision.sh with server CN localhost. The FIRST identity's pair is
    client.pem / client_key.pem; the rest are client_<id>.pem / _key.pem."""
    p = subprocess.run(["sh", PROVISION, out_dir, "localhost", *identities],
                       capture_output=True, text=True)
    assert p.returncode == 0, "mtls provisioning failed:\n" + p.stdout + p.stderr


def client_pair(pki, identity=None):
    """(cert, key) paths for `identity` in `pki` (None = the first identity)."""
    if identity is None:
        return (os.path.join(pki, "client.pem"), os.path.join(pki, "client_key.pem"))
    return (os.path.join(pki, "client_{}.pem".format(identity)),
            os.path.join(pki, "client_{}_key.pem".format(identity)))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@contextlib.contextmanager
def running_server(server_bin, pki, env_extra):
    """Start the server on a free localhost port with `env_extra` added to its
    environment (HARPIA_RBAC_MAP, HARPIA_SESSION_KEY, ...). Yields the port."""
    port = free_port()
    server = subprocess.Popen(
        [server_bin, "localhost:{}".format(port), os.path.join(pki, "ca.pem"),
         os.path.join(pki, "server.pem"), os.path.join(pki, "server_key.pem")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env={**os.environ, **env_extra})
    wait_for_listening(server)
    try:
        yield port
    finally:
        server.stdin.close()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
