"""transport-authn epic, task 4 -- admin / main / guest RBAC on the generated
REST / SOAP / gRPC transports.

Replaces the flat X-User/X-Pswd (REST), <credentials> (SOAP) and x-user/x-pswd
call-metadata (gRPC) credential gate with a three-role model, keyed on the
verified mTLS client-certificate subject CommonName, whenever the compliance
profile mandates hardened transport (the same predicate that turns on mTLS).

Three layers:

  * unit / standalone (g++): the fixed role x operation matrix as an
    allow/deny table (Compliance/runtime/harpia_rbac.h directly), the
    401/403/200 (UNAUTHENTICATED/PERMISSION_DENIED) decision mapping, and
    "exactly one AuditSink record per denial, metadata only".
  * REST + SOAP integration (protoc + g++ + pkg-config + openssl + vendored
    crow/asio): the generated HttpServer over real HTTPS -- an admin cert is
    served every verb, a guest cert is served reads but 403'd on writes, a
    valid-but-unmapped cert is 403'd, no client cert is refused at the TLS
    handshake.
  * gRPC integration (protoc + grpc_cpp_plugin + g++ + grpc++ + openssl):
    the generated GrpcServer over real mTLS -- same admin / guest / unmapped
    outcomes with PERMISSION_DENIED; an unauthenticated in-process call is
    UNAUTHENTICATED.

The flat-gate variant (low-risk profile) keeps its own coverage in
test_stage11_soap.py / test_stage12_rest.py / test_stage13.py.
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
RBAC_SRC = os.path.join(REPO_ROOT, "Compliance", "runtime", "harpia_rbac.h")
RBAC_RUNTIME_DIR = os.path.join(REPO_ROOT, "Compliance", "runtime")
CROW = os.path.join(REPO_ROOT, "third_party", "crow")
ASIO = os.path.join(REPO_ROOT, "third_party", "asio")
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


# ==========================================================================
# unit / standalone -- the mechanism (Compliance/runtime/harpia_rbac.h)
# ==========================================================================

_g = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")


def _build_run(tmp_path, name, src, env=None):
    srcp = tmp_path / (name + ".cpp")
    srcp.write_text(src, encoding="utf-8")
    binp = tmp_path / name
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", RBAC_RUNTIME_DIR, str(srcp), "-o", str(binp)],
        capture_output=True, text=True)
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    runenv = {**os.environ, **(env or {})}
    return subprocess.run([str(binp)], capture_output=True, text=True,
                          env=runenv, timeout=30)


@_g
def test_role_operation_matrix_is_the_expected_allow_deny_table(tmp_path):
    """harpia::rbac::permitted(role, op) for the full 4x7 table: admin = all,
    main = all but remove, guest = read/list/stream, none = nothing; heartBeat
    open to everyone (master plan section 0a -- one matrix per project)."""
    r = _build_run(tmp_path, "rbac_matrix", r'''
#include <cstdio>
#include "harpia_rbac.h"
using namespace harpia::rbac;

int main() {
    const Role roles[]   = { Role::none, Role::guest, Role::main, Role::admin };
    const Operation ops[] = { Operation::read, Operation::list, Operation::create,
                              Operation::update, Operation::remove,
                              Operation::stream, Operation::heartbeat };
    // expected[role_index][op_index]
    const bool want[4][7] = {
        /* none  */ { false, false, false, false, false, false, true },
        /* guest */ { true,  true,  false, false, false, true,  true },
        /* main  */ { true,  true,  true,  true,  false, true,  true },
        /* admin */ { true,  true,  true,  true,  true,  true,  true },
    };
    int fails = 0;
    for (int ri = 0; ri < 4; ++ri) {
        for (int oi = 0; oi < 7; ++oi) {
            const bool got = permitted(roles[ri], ops[oi]);
            if (got != want[ri][oi]) {
                std::printf("MISMATCH role=%s op=%s got=%d want=%d\n",
                            role_name(roles[ri]), op_name(ops[oi]),
                            got, want[ri][oi]);
                ++fails;
            }
        }
    }
    // parse_role / role_name round-trip for the real roles
    if (parse_role("admin") != Role::admin) ++fails;
    if (parse_role("main")  != Role::main)  ++fails;
    if (parse_role("guest") != Role::guest) ++fails;
    if (parse_role("nonsense") != Role::none) ++fails;
    return fails;
}
''')
    assert r.returncode == 0, "matrix mismatches:\n" + r.stdout + r.stderr


@_g
def test_decision_maps_no_identity_to_401_and_wrong_role_to_403(tmp_path):
    """decide() -> Decision::{unauthenticated, forbidden, allow}: empty CN ->
    unauthenticated (HTTP 401 / gRPC UNAUTHENTICATED); a verified-but-unmapped
    CN or a mapped CN whose role may not do the op -> forbidden (403 /
    PERMISSION_DENIED); the right role -> allow. heartBeat is always allow."""
    mapf = tmp_path / "roles.map"
    mapf.write_text("admin-id admin\nmain-id main\nguest-id guest\n",
                    encoding="utf-8")
    r = _build_run(tmp_path, "rbac_decision", r'''
#include <cstdio>
#include "harpia_rbac.h"
using namespace harpia::rbac;

static int expect(const char* label, Decision got, Decision want) {
    if (got == want) return 0;
    std::printf("FAIL %s: got=%d want=%d\n", label,
                static_cast<int>(got), static_cast<int>(want));
    return 1;
}

int main() {
    int f = 0;
    // no identity -> unauthenticated (401)
    f += expect("empty->create", decide("", Operation::create, "users"),
                Decision::unauthenticated);
    // verified identity, not in the map -> forbidden (403)
    f += expect("stranger->list", decide("stranger", Operation::list, "users"),
                Decision::forbidden);
    // mapped, but the role may not do this op -> forbidden (403)
    f += expect("guest->create", decide("guest-id", Operation::create, "users"),
                Decision::forbidden);
    // mapped, role permits -> allow (200)
    f += expect("guest->list", decide("guest-id", Operation::list, "users"),
                Decision::allow);
    f += expect("main->update", decide("main-id", Operation::update, "users"),
                Decision::allow);
    f += expect("main->remove", decide("main-id", Operation::remove, "users"),
                Decision::forbidden);
    f += expect("admin->remove", decide("admin-id", Operation::remove, "users"),
                Decision::allow);
    // heartBeat open even to an unauthenticated caller
    f += expect("empty->heartbeat", decide("", Operation::heartbeat, "users"),
                Decision::allow);
    return f;
}
''', env={"HARPIA_RBAC_MAP": str(mapf)})
    assert r.returncode == 0, r.stdout + r.stderr


@_g
def test_exactly_one_audit_record_per_denial_metadata_only(tmp_path):
    """Every non-allow decision emits exactly one AuditSink record
    ("rbac_denied"); an allow emits none. The record carries the operation, the
    subject (table) and a detail string of cn/role/op/decision metadata -- never
    a credential value (design-rules Rule 5: record() structurally cannot carry
    one)."""
    mapf = tmp_path / "roles.map"
    mapf.write_text("alice admin\nbob guest\n", encoding="utf-8")
    r = _build_run(tmp_path, "rbac_audit", r'''
#include <cstdio>
#include <string>
#include <vector>
#include "harpia_rbac.h"

struct Rec { std::string op, subject, detail; };

class RecordingSink : public ::harpia::compliance::AuditSink {
public:
    void record(const std::string& op, const std::string& subject,
                const std::string& detail = "") override {
        recs.push_back({op, subject, detail});
    }
    std::vector<Rec> recs;
};

using namespace harpia::rbac;

int main() {
    RecordingSink sink;
    // 3 denials ...
    decide("", Operation::create, "users_table", sink);        // unauthenticated
    decide("carol", Operation::create, "users_table", sink);   // unmapped
    decide("bob", Operation::create, "users_table", sink);     // guest !create
    // ... and 3 allows (must not record)
    decide("bob", Operation::read, "users_table", sink);
    decide("alice", Operation::remove, "users_table", sink);
    decide("", Operation::heartbeat, "users_table", sink);

    if (sink.recs.size() != 3) {
        std::printf("FAIL: %zu records, want 3\n", sink.recs.size());
        return 1;
    }
    int f = 0;
    for (const auto& rec : sink.recs) {
        if (rec.op != "rbac_denied") { std::printf("FAIL op=%s\n", rec.op.c_str()); ++f; }
        if (rec.subject != "users_table") { std::printf("FAIL subject=%s\n", rec.subject.c_str()); ++f; }
        // detail is metadata only: the four tokens, and nothing that could be a
        // credential value.
        for (const char* tok : {"cn=", "role=", "op=", "decision="}) {
            if (rec.detail.find(tok) == std::string::npos) {
                std::printf("FAIL detail %s missing %s\n", rec.detail.c_str(), tok);
                ++f;
            }
        }
    }
    if (sink.recs[0].detail.find("decision=unauthenticated") == std::string::npos) ++f;
    if (sink.recs[1].detail.find("role=none") == std::string::npos) ++f;
    if (sink.recs[2].detail.find("role=guest") == std::string::npos) ++f;
    if (sink.recs[2].detail.find("op=create") == std::string::npos) ++f;
    return f;
}
''', env={"HARPIA_RBAC_MAP": str(mapf)})
    assert r.returncode == 0, r.stdout + r.stderr


# ==========================================================================
# integration -- the generated transports under a hardened (RBAC) profile
# ==========================================================================
# The repo compliance profile is class_c / cloud_connected, so a plain
# run_pipeline.py generation is already hardened: the emitted gate is RBAC and
# the servers require mTLS. mtls_provision.sh issues one client cert per named
# identity (subject CN = the identity); the RBAC map binds those CNs to roles.

_ROLE_MAP = "admin admin\nmain main\nguest guest\n"


def _pkgconfig(*pkgs):
    def _run(*args):
        out = subprocess.run(["pkg-config", *args, *pkgs],
                             capture_output=True, text=True)
        return out.stdout.split() if out.returncode == 0 else []
    return _run


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_rbac")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    build = os.path.join(str(out), "build")

    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    certs = os.path.join(str(out), "pki")
    p = subprocess.run(["sh", PROVISION, certs, "localhost",
                        "admin", "main", "guest", "stranger"],
                       capture_output=True, text=True)
    assert p.returncode == 0, "mtls provisioning failed:\n" + p.stdout + p.stderr

    rbac_map = os.path.join(str(out), "rbac_map.txt")
    with open(rbac_map, "w", encoding="utf-8") as fh:
        fh.write(_ROLE_MAP)

    return {
        "tmp": str(out),
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "proto_dir": os.path.join(build, "generated", "cpp", "protofiles"),
        "certs": certs,
        "ca": os.path.join(certs, "ca.pem"),
        "server_cert": os.path.join(certs, "server.pem"),
        "server_key": os.path.join(certs, "server_key.pem"),
        "rbac_map": rbac_map,
    }


def _client_ctx(g, identity):
    ctx = ssl.create_default_context(cafile=g["ca"])
    ctx.check_hostname = False
    ctx.load_cert_chain(os.path.join(g["certs"], "client_{}.pem".format(identity)),
                        os.path.join(g["certs"], "client_{}_key.pem".format(identity)))
    return ctx


_http_toolchain = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "g++", "pkg-config"))
    or shutil.which("openssl") is None
    or not os.path.exists(os.path.join(ASIO, "asio", "ssl.hpp")),
    reason="needs protoc + g++ + pkg-config + openssl + vendored crow/asio",
)

_grpc_toolchain = pytest.mark.skipif(
    any(shutil.which(t) is None
        for t in ("protoc", "grpc_cpp_plugin", "g++", "pkg-config"))
    or shutil.which("openssl") is None
    or subprocess.run(["pkg-config", "--exists", "grpc++"]).returncode != 0,
    reason="needs protoc + grpc_cpp_plugin + g++ + grpc++ + openssl",
)


@_http_toolchain
def test_rest_and_soap_rbac_over_mtls(generated):
    g = generated
    cpp_root = g["cpp_root"]
    proto = g["proto_dir"]
    pc = _pkgconfig("protobuf")

    prog = os.path.join(g["tmp"], "rbac_https.cc")
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
            "    ::users s1; s1.set_id_{h}(1); s1.set_name(\"neo\");\n"
            "    ::users s2; s2.set_id_{h}(2); s2.set_name(\"trin\");\n"
            "    if (!dao.create(s1) || !dao.create(s2)) return 3;\n"
            '    harpia::http_transport::HttpServer server(db, "/v1", "/soap", mtls);\n'
            '    server.app().bindaddr("127.0.0.1").port(port).multithreaded();\n'
            "    std::thread t([&]{{ try {{ server.app().run(); }} catch (...) {{}} }});\n"
            "    server.app().wait_for_server_start();\n"
            '    std::cout << "READY" << std::endl;\n'
            "    std::string line; std::getline(std::cin, line);\n"
            "    server.stop();\n"
            "    t.join();\n"
            "    return 0;\n"
            "}}\n".format(h=HASH))

    objs = glob.glob(os.path.join(proto, "*.pb.cc"))
    binary = os.path.join(g["tmp"], "rbac_https")
    c = subprocess.run(
        ["g++", "-std=c++17", "-DASIO_STANDALONE", "-DCROW_ENABLE_SSL",
         "-I", cpp_root, "-I", CROW, "-I", ASIO, "-I", TINYXML2,
         *pc("--cflags"), prog, *objs, os.path.join(TINYXML2, "tinyxml2.cpp"),
         "-o", binary, "-lsoci_core", "-lsoci_sqlite3", *pc("--libs"),
         "-lssl", "-lcrypto", "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, "https server build failed:\n" + c.stderr

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    proc = subprocess.Popen(
        [binary, str(port), g["ca"], g["server_cert"], g["server_key"]],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env={**os.environ, "HARPIA_RBAC_MAP": g["rbac_map"]})

    def _die(msg):
        try:
            proc.stdin.close()
            rest = proc.stdout.read()
        except Exception:
            rest = ""
        proc.kill()
        raise AssertionError("{}\n--- server output ---\n{}".format(msg, rest))

    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            ln = proc.stdout.readline()
            if not ln:
                _die("server exited before READY")
            if ln.strip() == "READY":
                break
        else:
            _die("server did not print READY")
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)

        def rest_call(identity, method, path, body=None):
            conn = http.client.HTTPSConnection("127.0.0.1", port,
                                               context=_client_ctx(g, identity),
                                               timeout=15)
            headers = {"Content-Type": "application/json"} if body else {}
            conn.request(method, path, body=body, headers=headers)
            st = conn.getresponse().status
            conn.close()
            return st

        # The RBAC gate is the first statement in every route handler, so a
        # denied request never reaches body parsing -- the 403 cases below use
        # body-less verbs or a throwaway body interchangeably. The "allowed"
        # cases use body-less verbs (GET / DELETE) so no hand-built JSON is in
        # play.

        # guest -- reads allowed (200), writes forbidden (403)
        assert rest_call("guest", "GET", "/v1/users") == 200
        assert rest_call("guest", "GET", "/v1/users/1") == 200
        assert rest_call("guest", "POST", "/v1/users", "{}") == 403
        assert rest_call("guest", "DELETE", "/v1/users/1") == 403

        # main -- may create/update, but remove is 403
        assert rest_call("main", "DELETE", "/v1/users/1") == 403

        # valid cert, not in the map -> role none -> 403 on everything
        assert rest_call("stranger", "GET", "/v1/users") == 403

        # admin -- allowed on a mutating verb: DELETE row 2 -> 204, then gone
        assert rest_call("admin", "GET", "/v1/users") == 200
        assert rest_call("admin", "DELETE", "/v1/users/2") == 204
        assert rest_call("admin", "GET", "/v1/users/2") == 404

        # SOAP rides the same crow::SimpleApp; the gate moved after the op-name
        # parse. guest: set -> 403 Fault, get(row 1) -> 200. admin get -> 200.
        soap_env = ('<soap:Envelope xmlns:soap='
                    '"http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>')
        set_body = (soap_env + "<set><users><name>zion</name></users></set>"
                    "</soap:Body></soap:Envelope>")
        get_body = (soap_env + "<get><id>1</id></get>"
                    "</soap:Body></soap:Envelope>")

        def soap_call(identity, xml):
            conn = http.client.HTTPSConnection("127.0.0.1", port,
                                               context=_client_ctx(g, identity),
                                               timeout=15)
            conn.request("POST", "/soap/users", body=xml,
                         headers={"Content-Type": "text/xml"})
            resp = conn.getresponse()
            out = (resp.status, resp.read().decode("utf-8", "replace"))
            conn.close()
            return out

        st, txt = soap_call("guest", set_body)
        assert st == 403 and "Fault" in txt, (st, txt)
        st, txt = soap_call("guest", get_body)
        assert st == 200 and "getResponse" in txt, (st, txt)
        st, txt = soap_call("admin", get_body)
        assert st == 200 and "getResponse" in txt, (st, txt)

        # no client cert -> refused at the TLS handshake, never reaches the gate
        bare = ssl.create_default_context(cafile=g["ca"])
        bare.check_hostname = False
        with pytest.raises((ssl.SSLError, ConnectionError, OSError)):
            nc = http.client.HTTPSConnection("127.0.0.1", port, context=bare,
                                             timeout=15)
            nc.request("GET", "/v1/users")
            nc.getresponse()
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


@_grpc_toolchain
def test_grpc_rbac_over_mtls_and_unauthenticated_in_process(generated):
    g = generated
    from ProtoFile.GrpcCompiler import GrpcCompiler
    build = os.path.join(g["tmp"], "build")
    assert GrpcCompiler(dest=build).Process() is None, "Stage 13 failed"
    cpp_root = g["cpp_root"]
    proto = g["proto_dir"]
    pc = _pkgconfig("grpc++", "protobuf")

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    addr = "localhost:{}".format(port)

    prog = os.path.join(g["tmp"], "rbac_grpc.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "grpc/grpc_server_bringup.h"\n'
            '#include "db/users_{h}_crudl.h"\n'
            "#include <grpcpp/grpcpp.h>\n"
            "#include <soci/soci.h>\n"
            "#include <soci/sqlite3/soci-sqlite3.h>\n"
            "#include <chrono>\n"
            "#include <string>\n"
            "using namespace harpia::grpc_transport;\n"
            "static ::grpc::StatusCode push_as(\n"
            "        ::frameworkProtos::users_Service::Stub* stub, int id) {{\n"
            "    ::frameworkProtos::users_Message req;\n"
            "    req.mutable_msg()->set_id_{h}(id);\n"
            '    req.mutable_msg()->set_name("n");\n'
            "    ::grpc::ClientContext c;\n"
            "    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));\n"
            "    ::frameworkProtos::errorCode ec;\n"
            "    return stub->push(&c, req, &ec).error_code();\n"
            "}}\n"
            "static ::grpc::StatusCode list_as(\n"
            "        ::frameworkProtos::users_Service::Stub* stub) {{\n"
            "    ::grpc::ClientContext c;\n"
            "    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));\n"
            "    ::frameworkProtos::users_Stream req;\n"
            "    auto rd = stub->streamSrc(&c, req);\n"
            "    ::frameworkProtos::users_Message m;\n"
            "    while (rd->Read(&m)) {{}}\n"
            "    return rd->Finish().error_code();\n"
            "}}\n"
            "static std::unique_ptr< ::frameworkProtos::users_Service::Stub> mk(\n"
            "        const std::string& addr, const MtlsFiles& f) {{\n"
            "    return ::frameworkProtos::users_Service::NewStub(\n"
            "        ::grpc::CreateChannel(addr, channel_credentials(true, f)));\n"
            "}}\n"
            "int main(int, char** argv) {{\n"
            "    const std::string addr = argv[1];\n"
            "    const std::string ca = argv[2], scrt = argv[3], skey = argv[4];\n"
            "    const std::string cdir = argv[5];\n"
            "    MtlsFiles server_mtls{{ca, scrt, skey}};\n"
            '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    GrpcServer server(db, addr, server_mtls);\n"
            "    if (!server.ok()) return 3;\n"
            "    auto cf = [&](const char* who) {{\n"
            "        return MtlsFiles{{ca, cdir + \"/client_\" + who + \".pem\",\n"
            "                          cdir + \"/client_\" + who + \"_key.pem\"}};\n"
            "    }};\n"
            "    int rc = 0;\n"
            "    {{ auto s = mk(addr, cf(\"admin\"));\n"
            "       if (push_as(s.get(), 1) != ::grpc::StatusCode::OK) rc = 10;\n"
            "       if (list_as(s.get()) != ::grpc::StatusCode::OK) rc = 11; }}\n"
            "    {{ auto s = mk(addr, cf(\"guest\"));\n"
            "       if (push_as(s.get(), 2) != ::grpc::StatusCode::PERMISSION_DENIED) rc = 12;\n"
            "       if (list_as(s.get()) != ::grpc::StatusCode::OK) rc = 13; }}\n"
            "    {{ auto s = mk(addr, cf(\"stranger\"));\n"
            "       if (push_as(s.get(), 3) != ::grpc::StatusCode::PERMISSION_DENIED) rc = 14; }}\n"
            "    server.shutdown();\n"
            "    return rc;\n"
            "}}\n".format(h=HASH))

    objs = glob.glob(os.path.join(proto, "*.pb.cc"))
    binary = os.path.join(g["tmp"], "rbac_grpc")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, *pc("--cflags"),
         prog, *objs, "-o", binary, "-lsoci_core", "-lsoci_sqlite3",
         *pc("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, "grpc rbac build failed:\n" + c.stderr

    run = subprocess.run([binary, addr, g["ca"], g["server_cert"],
                          g["server_key"], g["certs"]],
                         capture_output=True, text=True, timeout=90,
                         env={**os.environ, "HARPIA_RBAC_MAP": g["rbac_map"]})
    assert run.returncode == 0, "grpc mTLS RBAC check #{} (stderr={!r})".format(
        run.returncode, run.stderr)

    # unauthenticated in-process call (no wire, no cert) -> UNAUTHENTICATED
    prog2 = os.path.join(g["tmp"], "rbac_grpc_anon.cc")
    with open(prog2, "w") as f:
        f.write(
            '#include "grpc/users_{h}_grpc.h"\n'
            "#include <grpcpp/grpcpp.h>\n"
            "#include <soci/soci.h>\n"
            "#include <soci/sqlite3/soci-sqlite3.h>\n"
            "int main() {{\n"
            '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    harpia::grpc_svc::users_service svc(db);\n"
            "    ::grpc::ServerBuilder b; b.RegisterService(&svc);\n"
            "    auto server = b.BuildAndStart();\n"
            "    if (!server) return 3;\n"
            "    auto chan = server->InProcessChannel(::grpc::ChannelArguments());\n"
            "    auto stub = ::frameworkProtos::users_Service::NewStub(chan);\n"
            "    ::frameworkProtos::users_Message req;\n"
            "    req.mutable_msg()->set_id_{h}(1);\n"
            "    ::grpc::ClientContext c;\n"
            "    ::frameworkProtos::errorCode ec;\n"
            "    auto st = stub->push(&c, req, &ec);\n"
            "    server->Shutdown();\n"
            "    return st.error_code() == ::grpc::StatusCode::UNAUTHENTICATED ? 0 : 4;\n"
            "}}\n".format(h=HASH))
    binary2 = os.path.join(g["tmp"], "rbac_grpc_anon")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, *pc("--cflags"),
         prog2, *objs, "-o", binary2, "-lsoci_core", "-lsoci_sqlite3",
         *pc("--libs"), "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, "grpc anon build failed:\n" + c.stderr
    run = subprocess.run([binary2], capture_output=True, text=True, timeout=60,
                         env={**os.environ, "HARPIA_RBAC_MAP": g["rbac_map"]})
    assert run.returncode == 0, "in-process unauthenticated check #{}".format(
        run.returncode)
