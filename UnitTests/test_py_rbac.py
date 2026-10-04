"""python-target / py-transports-http task 6: admin / main / guest RBAC
(``harpia_runtime.rbac`` + ``harpia_runtime.rbac_gates``) and the per-message
``protected`` / ``open`` gate choice on the generated REST / SOAP / gRPC
bindings.

- mechanism: the role x operation matrix, every ``decide()`` outcome and its
  ``rbac_denied`` audit text are identical to ``harpia_rbac.h`` (g++), for one
  map file in the C++ format (comments, CRLF, duplicates, unknown roles);
- gate choice: every generated binding uses RBAC exactly when the C++ one
  does (``Database.auth_gate.effective_rbac``), under the hardened profile
  (all but ``open`` reception_desk) and a low-risk one (only ``protected``
  vault);
- REST + SOAP over mTLS on the generated ``HttpServer``: the (identity, op)
  matrix -- admin / main / guest / unmapped cert / no cert -- 2xx / 401 /
  403, one value-free ``rbac_denied`` per denial; ``open`` reception_desk
  keeps the flat credential for a certless caller; **the C++ ``HttpServer``
  answers the same request sequence identically** (same certs, same map);
- gRPC with client certificates required: the same matrix as
  ``PERMISSION_DENIED``; the generated mixed-mode ``GrpcServer`` lets a
  certless caller reach the ``open`` message and answers ``UNAUTHENTICATED``
  for an RBAC one (the documented Python limitation: no client cert is ever
  seen in gRPC mixed mode).
"""
import contextlib
import http.client
import importlib
import os
import shutil
import socket
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests.test_py_rest import generate_low_risk  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY or shutil.which("openssl") is None,
                                reason=P.SKIP_PY + " + openssl")

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")
THIRD = os.path.join(REPO_ROOT, "third_party")
IDS = ("admin", "main", "guest", "stranger")
WHO = IDS + (None,)  # None: no client certificate
ROLE_MAP = ("# deployment role map\r\nadmin admin\r\nmain main   # trailing comment\r\n"
            "guest guest\r\nbogus superuser\r\nlater guest\r\nlater admin\r\n\r\nlonely\r\n")
OPS = ("read", "list", "create", "update", "remove", "stream", "heartbeat")
ENV = '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_rbac"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture(scope="module")
def low(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("py_rbac_low")
    os.makedirs(os.path.join(str(tmp), "out"))
    return generate_low_risk(tmp)


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("rbac_pki"))
    p = subprocess.run(["sh", PROVISION, d, "localhost", *IDS], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    out = {"dir": d, "ca": os.path.join(d, "ca.pem"), "cert": os.path.join(d, "server.pem"),
           "key": os.path.join(d, "server_key.pem")}
    for i in IDS:
        out[i] = (os.path.join(d, "client_%s.pem" % i), os.path.join(d, "client_%s_key.pem" % i))
    return out


@pytest.fixture(scope="module")
def role_map_file(tmp_path_factory):
    f = tmp_path_factory.mktemp("rbac_map") / "roles.map"
    f.write_bytes(ROLE_MAP.encode())
    return str(f)


class _Capture:
    def __init__(self):
        self.records = []

    def __call__(self):
        base = _mod("harpia_runtime.compliance.audit_sink").AuditSink
        outer = self

        class Sink(base):
            def record(self, operation, subject, detail=""):
                outer.records.append((operation, subject, detail))
        return Sink()


@pytest.fixture()
def rbac(gen, role_map_file, monkeypatch):
    """The generated project's runtime with HARPIA_RBAC_MAP loaded fresh and
    the default audit sink capturing."""
    P.activate(P.py_root(gen))
    return _arm(role_map_file, monkeypatch)


def _arm(role_map_file, monkeypatch):
    monkeypatch.setenv("HARPIA_RBAC_MAP", role_map_file)
    mod = _mod("harpia_runtime.rbac")
    monkeypatch.setattr(mod, "_ROLE_MAP", None)
    cap = _Capture()
    monkeypatch.setattr(_mod("harpia_runtime.compliance.audit_sink"), "_DEFAULT_SINK", cap())
    mod.records = cap.records
    return mod


# -- mechanism -------------------------------------------------------------------

_CPP_DECIDE = r'''
#include <cstdio>
#include "harpia_rbac.h"
using namespace harpia::rbac;
struct Cap : ::harpia::compliance::AuditSink {
    void record(const std::string& o, const std::string& s, const std::string& d) override {
        std::printf("audit %s|%s|%s\n", o.c_str(), s.c_str(), d.c_str());
    }
};
int main() {
    Cap cap;
    const char* cns[] = {"", "admin", "main", "guest", "stranger", "bogus", "later", "lonely"};
    const Role roles[] = {Role::none, Role::guest, Role::main, Role::admin};
    const Operation ops[] = {Operation::read, Operation::list, Operation::create,
        Operation::update, Operation::remove, Operation::stream, Operation::heartbeat};
    for (Role r : roles) for (Operation op : ops)
        std::printf("permitted %s %s %d\n", role_name(r), op_name(op), (int)permitted(r, op));
    for (const char* cn : cns) for (Operation op : ops)
        std::printf("decide %s %s %d\n", cn, op_name(op), (int)decide(cn, op, "users", cap));
    return 0;
}
'''


def _py_decide_lines(rbac):
    lines = []
    for r in ("none", "guest", "main", "admin"):
        for op in OPS:
            lines.append("permitted %s %s %d" % (
                r, op, int(rbac.permitted(rbac.Role(r), rbac.Operation(op)))))
    codes = {rbac.Decision.allow: 0, rbac.Decision.unauthenticated: 1,
             rbac.Decision.forbidden: 2}
    sink_cls = _mod("harpia_runtime.compliance.audit_sink").AuditSink

    class Printer(sink_cls):
        def record(self, operation, subject, detail=""):
            lines.append("audit %s|%s|%s" % (operation, subject, detail))
    sink = Printer()
    for cn in ("", "admin", "main", "guest", "stranger", "bogus", "later", "lonely"):
        for op in OPS:
            d = rbac.decide(cn, rbac.Operation(op), "users", sink)
            lines.append("decide %s %s %d" % (cn, op, codes[d]))
    return lines


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_decisions_and_audit_text_match_cpp(rbac, role_map_file, tmp_path):
    (tmp_path / "d.cpp").write_text(_CPP_DECIDE)
    c = subprocess.run(["g++", "-std=c++17", "-I", os.path.join(REPO_ROOT, "Compliance", "runtime"),
                        str(tmp_path / "d.cpp"), "-o", str(tmp_path / "d")],
                       capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    cpp = subprocess.run([str(tmp_path / "d")], capture_output=True, text=True, check=True,
                         env={**os.environ, "HARPIA_RBAC_MAP": role_map_file}).stdout
    py = _py_decide_lines(rbac)
    assert py == cpp.splitlines()
    assert any(line.startswith("audit rbac_denied|users|cn=<none> role=none op=read "
                               "decision=unauthenticated") for line in py)


def test_role_map_file_format(rbac, role_map_file, tmp_path, monkeypatch):
    m = rbac.RoleMap.from_file(role_map_file)
    assert [m.role_for(cn).value for cn in ("admin", "main", "guest", "bogus", "later",
                                            "lonely", "stranger", "")] == \
        ["admin", "main", "guest", "none", "admin", "none", "none", "none"]
    assert rbac.RoleMap.from_file(str(tmp_path / "missing")).empty()
    monkeypatch.delenv("HARPIA_RBAC_MAP")
    assert rbac.RoleMap.from_env().empty()
    # role_map() is loaded once: later environment changes are not seen
    monkeypatch.setenv("HARPIA_RBAC_MAP", role_map_file)
    assert rbac.role_map().role_for("admin") is rbac.Role.admin
    monkeypatch.setenv("HARPIA_RBAC_MAP", str(tmp_path / "missing"))
    assert rbac.role_map().role_for("admin") is rbac.Role.admin


def test_no_map_forbids_every_data_operation(rbac, monkeypatch):
    monkeypatch.delenv("HARPIA_RBAC_MAP")
    for op in OPS[:-1]:
        assert rbac.decide("admin", rbac.Operation(op), "users") is rbac.Decision.forbidden
    assert rbac.decide("", rbac.Operation.heartbeat, "users") is rbac.Decision.allow
    assert len(rbac.records) == len(OPS) - 1


# -- per-message gate choice -------------------------------------------------------

def _cpp_rbac_kinds(gen):
    cpp = os.path.join(gen, "generated", "cpp")
    out = {}
    for kind, ext, marker in (("rest", "_rest.h", "authz_"), ("soap", "_soap.h", "rbac::decide"),
                              ("grpc", "_grpc.h", "rbac_check")):
        for f in os.listdir(os.path.join(cpp, kind)):
            if f.endswith(ext) and HASH in f:
                name = f[:-len(ext)].rsplit("_", 1)[0]
                out[(kind, name)] = marker in open(os.path.join(cpp, kind, f)).read()
    return out


def _py_rbac_kinds(gen):
    root = os.path.join(P.py_root(gen), "harpia_generated")
    out = {}
    for kind, marker in (("rest", "rest_rbac_gate("), ("soap", "soap_rbac_gate("),
                         ("grpc", "grpc_rbac_gate(")):
        for f in os.listdir(os.path.join(root, kind)):
            if f.endswith("_%s.py" % kind) and HASH in f:
                name = f[:-len("_%s.py" % kind)].rsplit("_", 1)[0]
                out[(kind, name)] = marker in open(os.path.join(root, kind, f)).read()
    return out


def test_gate_choice_matches_cpp(gen, low):
    hard_kinds, low_kinds = _py_rbac_kinds(gen), _py_rbac_kinds(low)
    assert hard_kinds == _cpp_rbac_kinds(gen)
    assert low_kinds == _cpp_rbac_kinds(low)
    assert {n for (_, n), r in hard_kinds.items() if not r} == {"reception_desk"}
    assert {n for (_, n), r in low_kinds.items() if r} == {"vault"}
    rt = os.path.join(P.py_root(low), "harpia_runtime")
    assert os.path.exists(os.path.join(rt, "rbac.py"))
    assert os.path.exists(os.path.join(rt, "rbac_gates.py"))


# -- REST + SOAP over mTLS -----------------------------------------------------------

def _client_ctx(pki, who):
    import ssl
    ctx = ssl.create_default_context(cafile=pki["ca"])
    if who is not None:
        ctx.load_cert_chain(*pki[who])
    return ctx


def _request(port, ctx, method, path, body=None, headers=None):
    conn = http.client.HTTPSConnection("localhost", port, context=ctx, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        return r.status, r.read().decode()
    finally:
        conn.close()


def _user_json(pk, name):
    m = _mod("harpia_generated.protofiles.users_{h}_pb2").users()
    setattr(m, PK, pk)
    m.name = name
    return _mod("harpia_runtime.json").to_json(m)


def _user_xml(pk, name):
    m = _mod("harpia_generated.protofiles.users_{h}_pb2").users()
    setattr(m, PK, pk)
    m.name = name
    return _mod("harpia_runtime.xml").to_xml(m)


def _soap(body):
    return ENV + "<soap:Body>" + body + "</soap:Body></soap:Envelope>"


def http_sequence(i):
    """(label, op, method, path, body, headers) for identity number ``i``."""
    js = {"Content-Type": "application/json"}
    xml = {"Content-Type": "text/xml"}
    return [
        ("rest list", "list", "GET", "/v1/users", None, {}),
        ("rest read", "read", "GET", "/v1/users/1", None, {}),
        ("rest create", "create", "POST", "/v1/users", _user_json(100 + i, "secret-%d" % i), js),
        ("rest update", "update", "PUT", "/v1/users/1", _user_json(1, "secret-u%d" % i), js),
        ("rest remove", "remove", "DELETE", "/v1/users/%d" % (100 + i), None, {}),
        ("soap get", "read", "POST", "/soap/users", _soap("<get><id>1</id></get>"), xml),
        ("soap set", "create", "POST", "/soap/users",
         _soap("<set>" + _user_xml(200 + i, "secret-s%d" % i) + "</set>"), xml),
        ("soap update", "update", "POST", "/soap/users",
         _soap("<update>" + _user_xml(1, "secret-v%d" % i) + "</update>"), xml),
        ("soap delete", "remove", "POST", "/soap/users",
         _soap("<delete><id>%d</id></delete>" % (200 + i)), xml),
        ("soap unknown", None, "POST", "/soap/users", _soap("<frobnicate/>"), xml),
        ("open flat", None, "GET", "/v1/reception_desk", None,
         {"X-User": "reception_desk", "X-Pswd": HASH}),
        ("open no-cred", None, "GET", "/v1/reception_desk", None, {}),
    ]


def drive(port, pki):
    out = []
    for i, who in enumerate(WHO):
        ctx = _client_ctx(pki, who)
        for label, op, method, path, body, headers in http_sequence(i):
            status, text = _request(port, ctx, method, path, body, headers)
            out.append(("%s %s" % (who, label), op, status, text))
    return out


_ALLOWED = {"rest list": 200, "rest read": 200, "rest create": 201, "rest update": 204,
            "rest remove": 204}


def _py_http(pki, tmp_path):
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "rbac.db"), size=4)
    with pool.borrow() as conn:
        dao = _mod("harpia_generated.db.users_{h}_dao").users_dao(conn)
        dao.create_table()
        users = _mod("harpia_generated.protofiles.users_{h}_pb2").users
        for pk, name in ((1, "neo"), (2, "trin")):
            m = users()
            setattr(m, PK, pk)
            m.name = name
            dao.create(m)
        _mod("harpia_generated.db.reception_desk_{h}_dao").reception_desk_dao(
            conn).create_table()
    tls = _mod("harpia_runtime.tls")
    srv = _mod("harpia_generated.http.http_server_bringup").HttpServer(
        pool, host="localhost", rest_base="/v1", soap_base="/soap",
        mtls=tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]))
    srv.start()
    return srv


def test_rest_and_soap_matrix(rbac, pki, tmp_path):
    srv = _py_http(pki, tmp_path)
    try:
        got = drive(srv.port, pki)
    finally:
        srv.stop()
    m = rbac.RoleMap.from_file(os.environ["HARPIA_RBAC_MAP"])
    denials = 0
    for label, op, status, text in got:
        who, kind = label.split(" ", 1)
        cn = "" if who == "None" else who
        if op is None:
            want = 401 if kind == "open no-cred" else 200
        elif not cn:
            want, denials = 401, denials + 1
        elif not rbac.permitted(m.role_for(cn), rbac.Operation(op)):
            want, denials = 403, denials + 1
        else:
            want = _ALLOWED.get(kind, 200)
        assert status == want, (label, status, text)
        if kind.startswith("soap") and status in (401, 403):
            assert "<faultcode>Client.Authentication</faultcode><faultstring>%s</faultstring>" % (
                "unauthenticated" if status == 401 else "forbidden") in text
    assert len(rbac.records) == denials
    for operation, subject, detail in rbac.records:
        assert (operation, subject) == ("rbac_denied", "users")
        assert "secret" not in detail and "neo" not in detail
        assert detail.startswith("cn=") and " role=" in detail and " decision=" in detail


_CPP_HTTP = r'''
#include "http/http_server_bringup.h"
#include "db/users_%(h)s_crudl.h"
#include "db/reception_desk_%(h)s_crudl.h"
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include <iostream>
#include <string>
#include <thread>
int main(int, char** argv) {
    crow::logger::setLogLevel(crow::LogLevel::Critical);
    const int port = std::stoi(argv[1]);
    harpia::http_transport::MtlsFiles mtls{argv[2], argv[3], argv[4]};
    ::soci::session db(::soci::sqlite3, ":memory:");
    harpia::db::users_dao dao(db);
    if (!dao.create_table()) return 2;
    if (!harpia::db::reception_desk_dao(db).create_table()) return 2;
    ::users s1; s1.set_id_%(h)s(1); s1.set_name("neo");
    ::users s2; s2.set_id_%(h)s(2); s2.set_name("trin");
    if (!dao.create(s1) || !dao.create(s2)) return 3;
    harpia::http_transport::HttpServer server(db, "/v1", "/soap", mtls);
    server.app().bindaddr("127.0.0.1").port(port).multithreaded();
    std::thread t([&]{ try { server.app().run(); } catch (...) {} });
    server.app().wait_for_server_start();
    std::cout << "READY" << std::endl;
    std::string line; std::getline(std::cin, line);
    server.stop();
    t.join();
    return 0;
}
'''


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


HAVE_CPP_HTTP = (shutil.which("g++") is not None and shutil.which("pkg-config") is not None
                 and os.path.exists(os.path.join(THIRD, "asio", "asio", "ssl.hpp")))


def build_cpp_http(gen, tmp_path):
    """Link the generated C++ ``HttpServer`` (mTLS, ``/v1`` + ``/soap``,
    users rows 1 and 2, reception_desk) of ``gen``; returns the binary."""
    import glob
    cpp_root = os.path.join(gen, "generated", "cpp")
    (tmp_path / "s.cpp").write_text(_CPP_HTTP % {"h": HASH})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = str(tmp_path / "s")
    c = subprocess.run(
        ["g++", "-std=c++17", "-DASIO_STANDALONE", "-DCROW_ENABLE_SSL", "-I", cpp_root,
         "-I", os.path.join(THIRD, "crow"), "-I", os.path.join(THIRD, "asio"),
         "-I", os.path.join(THIRD, "tinyxml2"), str(tmp_path / "s.cpp"),
         *(f for f in glob.glob(os.path.join(cpp_root, "protofiles", "*.pb.cc"))
           if not f.endswith(".grpc.pb.cc")),
         os.path.join(THIRD, "tinyxml2", "tinyxml2.cpp"), "-o", exe,
         "-lsoci_core", "-lsoci_sqlite3", *flags, "-lssl", "-lcrypto", "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=900)
    assert c.returncode == 0, c.stderr[-4000:]
    return exe


@contextlib.contextmanager
def running_cpp_http(exe, pki, env):
    """Serve ``exe`` on a free port with ``env`` added; yields the port."""
    port = _free_port()
    proc = subprocess.Popen([exe, str(port), pki["ca"], pki["cert"], pki["key"]],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                            env={**os.environ, **env})
    try:
        assert proc.stdout.readline().strip() == "READY"
        yield port
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)


@pytest.mark.skipif(not HAVE_CPP_HTTP, reason="needs g++ + pkg-config + vendored crow/asio")
def test_same_answers_as_cpp_http_server(rbac, pki, role_map_file, gen, tmp_path):
    exe = build_cpp_http(gen, tmp_path)
    with running_cpp_http(exe, pki, {"HARPIA_RBAC_MAP": role_map_file}) as port:
        cpp = drive(port, pki)
    srv = _py_http(pki, tmp_path)
    try:
        py = drive(srv.port, pki)
    finally:
        srv.stop()

    def comparable(rows):
        # REST bodies of an empty-bodied error are Crow's default status line
        # there and empty here; every SOAP envelope is compared byte for byte
        return [(label, status, text if label.split(" ", 1)[1].startswith("soap") else None)
                for label, _, status, text in rows]
    assert comparable(py) == comparable(cpp)


# -- gRPC ------------------------------------------------------------------------

def _grpc_svc(name="users"):
    return _mod("harpia_generated.protofiles.%s_{h}_service_pb2" % name)


def _grpc_pool(tmp_path):
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "g.db"), size=4)
    with pool.borrow() as conn:
        dao = _mod("harpia_generated.db.users_{h}_dao").users_dao(conn)
        dao.create_table()
        m = _mod("harpia_generated.protofiles.users_{h}_pb2").users()
        setattr(m, PK, 1)
        m.name = "neo"
        dao.create(m)
        _mod("harpia_generated.db.reception_desk_{h}_dao").reception_desk_dao(
            conn).create_table()
    return pool


def _grpc_calls(ch, i, md=None):
    """op -> status code name for users' four RPCs."""
    import grpc
    stub = _mod("harpia_generated.protofiles.users_{h}_service_pb2_grpc").users_ServiceStub(ch)
    svc = _grpc_svc()
    push = svc.users_Message()
    setattr(push.msg, PK, 300 + i)
    push.msg.name = "secret-g%d" % i
    calls = {
        "create": lambda: stub.push(push, metadata=md, timeout=10),
        "read": lambda: stub.pullByID(svc.users_ID(id=1), metadata=md, timeout=10),
        "stream": lambda: list(stub.streamSrc(svc.users_Stream(), metadata=md, timeout=10)),
        "heartbeat": lambda: stub.heartBeat(svc.users_HeartBeat(), timeout=10),
    }
    out = {}
    for op, call in calls.items():
        try:
            call()
            out[op] = "OK"
        except grpc.RpcError as e:
            out[op] = "%s %s" % (e.code().name, e.details())
    return out


def test_grpc_matrix_client_certs_required(rbac, pki, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    import grpc
    tls = _mod("harpia_runtime.tls")
    mod = _mod("harpia_generated.grpc.users_{h}_grpc")
    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    mod.add_to_server(mod.users_Service(_grpc_pool(tmp_path)), server)
    port = server.add_secure_port("localhost:0", tls.grpc_server_credentials(
        True, tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]), True))
    server.start()
    m = rbac.RoleMap.from_file(os.environ["HARPIA_RBAC_MAP"])
    try:
        for i, who in enumerate(IDS):
            ch = grpc.secure_channel("localhost:%d" % port, tls.grpc_channel_credentials(
                tls.MtlsFiles(pki["ca"], *pki[who])))
            try:
                got = _grpc_calls(ch, i)
            finally:
                ch.close()
            want = {op: "OK" if rbac.permitted(m.role_for(who), rbac.Operation(op))
                    else "PERMISSION_DENIED forbidden" for op in got}
            assert got == want, who
    finally:
        server.stop(None).wait()
    assert rbac.records and all(r[0] == "rbac_denied" and "secret" not in r[2]
                                for r in rbac.records)


def test_grpc_mixed_mode_open_vs_rbac(rbac, pki, tmp_path):
    import grpc
    tls = _mod("harpia_runtime.tls")
    bring = _mod("harpia_generated.grpc.grpc_server_bringup")
    assert (bring.EMIT_TLS, bring.CLIENT_CERT_REQUIRED) == (True, False)
    srv = bring.GrpcServer(_grpc_pool(tmp_path), "localhost:0",
                           mtls=tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]))
    srv.start()
    certless = grpc.ssl_channel_credentials(root_certificates=open(pki["ca"], "rb").read())
    admin = tls.grpc_channel_credentials(tls.MtlsFiles(pki["ca"], *pki["admin"]))
    try:
        for creds in (certless, admin):
            ch = grpc.secure_channel("localhost:%d" % srv.port, creds)
            try:
                got = _grpc_calls(ch, 0)
                desk = _mod("harpia_generated.protofiles.reception_desk_{h}_service_pb2_grpc"
                            ).reception_desk_ServiceStub(ch)
                svc = _grpc_svc("reception_desk")
                with pytest.raises(grpc.RpcError) as e:  # open: flat gate passed, no row
                    desk.pullByID(svc.reception_desk_ID(id=1), timeout=10, metadata=(
                        ("x-user", "reception_desk"), ("x-pswd", HASH)))
                assert e.value.code() == grpc.StatusCode.NOT_FOUND
            finally:
                ch.close()
            # documented limitation: never a client certificate in mixed mode
            assert got == {"create": "UNAUTHENTICATED unauthenticated",
                           "read": "UNAUTHENTICATED unauthenticated",
                           "stream": "UNAUTHENTICATED unauthenticated",
                           "heartbeat": "OK"}
    finally:
        srv.stop()


# -- low-risk profile: only the protected message is RBAC-gated ---------------------

def test_low_risk_protected_message(low, pki, role_map_file, monkeypatch, tmp_path):
    P.activate(P.py_root(low))
    rbac = _arm(role_map_file, monkeypatch)
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "l.db"), size=4)
    with pool.borrow() as conn:
        for name in ("users", "vault"):
            getattr(_mod("harpia_generated.db.%s_{h}_dao" % name), name + "_dao")(
                conn).create_table()
    tls = _mod("harpia_runtime.tls")
    srv = _mod("harpia_generated.http.http_server_bringup").HttpServer(
        pool, host="localhost", mtls=tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]))
    srv.start()
    try:
        certless, guest = _client_ctx(pki, None), _client_ctx(pki, "guest")
        flat = {"X-User": "users", "X-Pswd": HASH}
        assert _request(srv.port, certless, "GET", "/users", headers=flat)[0] == 200
        assert _request(srv.port, certless, "GET", "/vault")[0] == 401
        assert _request(srv.port, guest, "GET", "/vault")[0] == 200
        assert _request(srv.port, guest, "DELETE", "/vault/1")[0] == 403
    finally:
        srv.stop()
    assert [r[2].rsplit(" ", 1)[1] for r in rbac.records] == \
        ["decision=unauthenticated", "decision=forbidden"]
