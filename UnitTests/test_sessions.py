"""transport-authn epic, task 5 -- bearer session tokens on the generated
REST / SOAP / gRPC transports.

Layered ON TOP OF the task-4 RBAC gate: once a caller has authenticated the
mTLS transport (client cert -> a verified CN -> an RBAC role) it can obtain a
signed bearer token and present that on subsequent calls instead of
re-deriving its identity from the certificate every time. The token carries
the CN, the role and an expiry; a revocation list is consulted on every call.
Signing is HMAC-SHA256 (OpenSSL); the key is deployment configuration
(HARPIA_SESSION_KEY), the same posture as the RBAC map file.

Three layers, mirroring test_rbac.py:

  * unit / standalone (g++ + -lcrypto): the mechanism
    (Compliance/runtime/harpia_session.h) directly -- issue/verify round trip,
    the role in a token matches the issuing identity, an expired token is
    rejected, a revoked token is rejected (and un-revoked again -- the list is
    re-read when it changes), a tampered / malformed token is rejected, and
    exactly one AuditSink "session_denied" record per non-ok verdict, metadata
    only.
  * REST + SOAP integration (protoc + g++ + pkg-config + openssl + vendored
    crow/asio): the generated HttpServer over real HTTPS -- POST /session
    mints a token for an mTLS-authenticated caller; a later call presenting
    `Authorization: Bearer <token>` is gated on the token's identity (an admin
    token used from a guest client cert still gets the admin verbs); an
    expired or revoked token is 401.
  * gRPC integration (protoc + grpc_cpp_plugin + g++ + grpc++ + openssl): the
    generated GrpcServer over real mTLS -- heartBeat() with
    `harpia-issue-session` metadata returns a `harpia-session-token`; a later
    push() presenting `authorization: Bearer <token>` is gated on the token's
    identity; a bad token is UNAUTHENTICATED.

The RBAC-only behaviour (no token presented) keeps its own coverage in
test_rbac.py; the flat-gate variant compiles no session code at all
(test_stage11/12/13).
"""
import glob
import http.client
import os
import re
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
SESSION_RUNTIME_DIR = os.path.join(REPO_ROOT, "Compliance", "runtime")
CROW = os.path.join(REPO_ROOT, "third_party", "crow")
ASIO = os.path.join(REPO_ROOT, "third_party", "asio")
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
SIGNING_KEY = "harpia-test-session-signing-key-0123456789"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_g = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")


# ==========================================================================
# unit / standalone -- the mechanism (Compliance/runtime/harpia_session.h)
# ==========================================================================

def _build_run(tmp_path, name, src, env=None):
    srcp = tmp_path / (name + ".cpp")
    srcp.write_text(src, encoding="utf-8")
    binp = tmp_path / name
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", SESSION_RUNTIME_DIR, str(srcp), "-o", str(binp)],
        capture_output=True, text=True)
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    runenv = {**os.environ, **(env or {})}
    return subprocess.run([str(binp)], capture_output=True, text=True,
                          env=runenv, timeout=30)


@_g
def test_issue_verify_round_trip_and_role_matches_identity(tmp_path):
    """issue() mints a token carrying the caller's CN + RBAC role + an expiry;
    verify() accepts it within its lifetime and hands the claims back, and the
    role in the token is exactly the role issue() was given."""
    r = _build_run(tmp_path, "sess_roundtrip", r'''
#include <cstdio>
#include "harpia_session.h"
using namespace harpia::session;
int main() {
    const std::string tok = issue("clinician-42", "main", 300, 1000);
    if (tok.empty()) { std::puts("FAIL: empty token"); return 1; }
    Claims c;
    if (verify(tok, &c, /*now=*/1100) != Verdict::ok) {
        std::puts("FAIL: verify != ok"); return 1;
    }
    int f = 0;
    if (c.cn != "clinician-42") { std::printf("cn=%s\n", c.cn.c_str()); ++f; }
    if (c.role != "main")       { std::printf("role=%s\n", c.role.c_str()); ++f; }
    if (c.issued_at != 1000)    { std::printf("iat=%lld\n", c.issued_at); ++f; }
    if (c.expires_at != 1300)   { std::printf("exp=%lld\n", c.expires_at); ++f; }
    if (c.jti.size() != 32)     { std::printf("jti=%s\n", c.jti.c_str()); ++f; }
    // a guest token carries "guest", not whatever the caller wishes
    Claims g;
    verify(issue("visitor", "guest", 300, 1000), &g, 1100);
    if (g.role != "guest") { std::printf("guest role=%s\n", g.role.c_str()); ++f; }
    return f;
}
''', env={"HARPIA_SESSION_KEY": SIGNING_KEY})
    assert r.returncode == 0, r.stdout + r.stderr


@_g
def test_expired_token_is_rejected(tmp_path):
    """A token whose expiry has passed is Verdict::expired -- the gate maps
    that to 401 / UNAUTHENTICATED."""
    r = _build_run(tmp_path, "sess_expired", r'''
#include <cstdio>
#include "harpia_session.h"
using namespace harpia::session;
int main() {
    const std::string tok = issue("u", "admin", /*ttl=*/60, /*now=*/1000);
    Claims c;
    if (verify(tok, &c, /*now=*/1059) != Verdict::ok)      return 1;  // still valid
    if (verify(tok, &c, /*now=*/1060) != Verdict::expired) return 2;  // at expiry
    if (verify(tok, &c, /*now=*/9999) != Verdict::expired) return 3;
    return 0;
}
''', env={"HARPIA_SESSION_KEY": SIGNING_KEY})
    assert r.returncode == 0, r.stdout + r.stderr


@_g
def test_revoked_token_is_rejected_and_list_is_reread_on_change(tmp_path):
    """A token whose jti is on the HARPIA_SESSION_REVOCATIONS file is
    Verdict::revoked; the file is re-read whenever its contents change, so a
    revocation (and an un-revocation) takes effect without a restart."""
    revf = tmp_path / "revocations.txt"
    revf.write_text("# none yet\n", encoding="utf-8")
    r = _build_run(tmp_path, "sess_revoked", r'''
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include "harpia_session.h"
using namespace harpia::session;
int main() {
    const char* rev = std::getenv("HARPIA_SESSION_REVOCATIONS");
    const std::string tok = issue("u", "admin", 3600, 1000);
    Claims c;
    if (verify(tok, &c, 1100) != Verdict::ok) return 1;
    { std::ofstream f(rev, std::ios::trunc);
      f << "# revoked below\n" << c.jti << "\n"; }
    if (verify(tok, &c, 1100) != Verdict::revoked) return 2;
    { std::ofstream f(rev, std::ios::trunc); f << "# cleared\n"; }
    if (verify(tok, &c, 1100) != Verdict::ok) return 3;
    return 0;
}
''', env={"HARPIA_SESSION_KEY": SIGNING_KEY,
          "HARPIA_SESSION_REVOCATIONS": str(revf)})
    assert r.returncode == 0, r.stdout + r.stderr


@_g
def test_tampered_and_malformed_tokens_are_rejected(tmp_path):
    """A token whose payload or MAC has been altered is Verdict::bad_signature;
    a structurally broken string is Verdict::malformed; with no signing key
    configured every verify() is Verdict::no_key (fail-safe)."""
    r = _build_run(tmp_path, "sess_tamper", r'''
#include <cstdio>
#include <cstdlib>
#include "harpia_session.h"
using namespace harpia::session;
int main() {
    if (std::getenv("HARPIA_SESSION_KEY") == nullptr) {
        // no-key build: issue refuses, verify refuses
        if (!issue("u", "admin").empty()) return 10;
        Claims c;
        if (verify("v1.abc.def", &c) != Verdict::no_key) return 11;
        return 0;
    }
    const std::string a = issue("u", "admin", 3600, 1000);
    const std::string b = issue("v", "guest", 3600, 1000);
    Claims c;
    // flip a bit of the MAC -> bad_signature
    std::string flip_mac = a; flip_mac[flip_mac.size() - 1] ^= 0x1;
    if (verify(flip_mac, &c, 1100) != Verdict::bad_signature) return 1;
    // A's payload spliced onto B's (real, but wrong) MAC -> bad_signature
    std::string spliced = a.substr(0, a.rfind('.') + 1) + b.substr(b.rfind('.') + 1);
    if (verify(spliced, &c, 1100) != Verdict::bad_signature) return 2;
    if (verify("not a token", &c, 1100)  != Verdict::malformed) return 3;
    if (verify("v1..",        &c, 1100)  != Verdict::malformed) return 4;
    if (verify("",            &c, 1100)  != Verdict::malformed) return 5;
    return 0;
}
''', env={"HARPIA_SESSION_KEY": SIGNING_KEY})
    assert r.returncode == 0, "with key:\n" + r.stdout + r.stderr
    r2 = _build_run(tmp_path, "sess_tamper", r'''
#include <cstdlib>
#include "harpia_session.h"
using namespace harpia::session;
int main() {
    if (!issue("u", "admin").empty()) return 10;
    Claims c;
    return verify("v1.abc.def", &c) == Verdict::no_key ? 0 : 11;
}
''', env={"HARPIA_SESSION_KEY": ""})
    assert r2.returncode == 0, "no key:\n" + r2.stdout + r2.stderr


@_g
def test_exactly_one_audit_record_per_non_ok_verdict_metadata_only(tmp_path):
    """Every non-ok verify() emits exactly one AuditSink "session_denied"
    record; an ok verify() emits none. The detail carries the verdict, the CN
    and the jti as metadata -- never the token string (Rule 5)."""
    revf = tmp_path / "rev.txt"
    revf.write_text("", encoding="utf-8")
    r = _build_run(tmp_path, "sess_audit", r'''
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
#include "harpia_session.h"

struct Rec { std::string op, subject, detail; };
class RecordingSink : public ::harpia::compliance::AuditSink {
public:
    void record(const std::string& op, const std::string& subject,
                const std::string& detail = "") override {
        recs.push_back({op, subject, detail});
    }
    std::vector<Rec> recs;
};
using namespace harpia::session;

int main() {
    RecordingSink sink;
    const std::string good = issue("alice", "admin", 3600, 1000);
    Claims c; decode(good, &c);
    const std::string full = good;                       // valid
    std::string tampered = good; tampered[tampered.size() - 1] ^= 1;

    verify(full, &c, 1100, sink);                        // ok        -> 0 recs
    verify(tampered, &c, 1100, sink);                    // bad_sig   -> 1 rec
    verify("garbage", &c, 1100, sink);                   // malformed -> 1 rec
    verify(issue("bob", "guest", 1, 10), &c, 100, sink); // expired   -> 1 rec
    { std::ofstream f(std::getenv("HARPIA_SESSION_REVOCATIONS"), std::ios::trunc);
      f << c.jti << "\n"; }
    verify(good, &c, 1100, sink);                        // revoked   -> 1 rec

    if (sink.recs.size() != 4) {
        std::printf("FAIL: %zu records, want 4\n", sink.recs.size());
        return 1;
    }
    int f = 0;
    for (const auto& rec : sink.recs) {
        if (rec.op != "session_denied") { std::printf("op=%s\n", rec.op.c_str()); ++f; }
        if (rec.subject != "session")   { std::printf("subj=%s\n", rec.subject.c_str()); ++f; }
        for (const char* tok : {"verdict=", "cn=", "jti="})
            if (rec.detail.find(tok) == std::string::npos) {
                std::printf("detail %s missing %s\n", rec.detail.c_str(), tok); ++f;
            }
        if (rec.detail.find(good) != std::string::npos ||
            rec.detail.find("v1.") != std::string::npos) {
            std::puts("FAIL: token material leaked into an audit detail"); ++f;
        }
    }
    return f;
}
''', env={"HARPIA_SESSION_KEY": SIGNING_KEY,
          "HARPIA_SESSION_REVOCATIONS": str(revf)})
    assert r.returncode == 0, r.stdout + r.stderr


# ==========================================================================
# integration -- the generated transports under a hardened (RBAC) profile
# ==========================================================================
# The repo compliance profile is class_c / cloud_connected, so a plain
# run_pipeline.py generation is already hardened: the emitted gate is RBAC + the
# session path, and the servers require mTLS. mtls_provision.sh issues one client
# cert per identity (subject CN = the identity); the RBAC map binds those CNs to
# roles; HARPIA_SESSION_KEY is handed to the server so it can sign tokens.

_ROLE_MAP = "admin admin\nmain main\nguest guest\n"


def _pkgconfig(*pkgs):
    def _run(*args):
        out = subprocess.run(["pkg-config", *args, *pkgs],
                             capture_output=True, text=True)
        return out.stdout.split() if out.returncode == 0 else []
    return _run


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_sessions")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    build = os.path.join(str(out), "build")

    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    certs = os.path.join(str(out), "pki")
    p = subprocess.run(["sh", PROVISION, certs, "localhost",
                        "admin", "main", "guest"],
                       capture_output=True, text=True)
    assert p.returncode == 0, "mtls provisioning failed:\n" + p.stdout + p.stderr

    rbac_map = os.path.join(str(out), "rbac_map.txt")
    with open(rbac_map, "w", encoding="utf-8") as fh:
        fh.write(_ROLE_MAP)
    revocations = os.path.join(str(out), "revocations.txt")
    with open(revocations, "w", encoding="utf-8") as fh:
        fh.write("# none\n")

    return {
        "tmp": str(out),
        "cpp_root": os.path.join(build, "generated", "cpp"),
        "proto_dir": os.path.join(build, "generated", "cpp", "protofiles"),
        "certs": certs,
        "ca": os.path.join(certs, "ca.pem"),
        "server_cert": os.path.join(certs, "server.pem"),
        "server_key": os.path.join(certs, "server_key.pem"),
        "rbac_map": rbac_map,
        "revocations": revocations,
    }


def _server_env(g):
    return {**os.environ,
            "HARPIA_RBAC_MAP": g["rbac_map"],
            "HARPIA_SESSION_KEY": SIGNING_KEY,
            "HARPIA_SESSION_REVOCATIONS": g["revocations"]}


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


# a tiny helper that mints a token off the same signing key / an arbitrary
# now+ttl, so the tests can fabricate an already-expired token deterministically
# without touching the server's own clock. Prints "<token>\t<jti>".
_MINT_SRC = r'''
#include <cstdio>
#include <string>
#include "harpia_session.h"
int main(int argc, char** argv) {
    if (argc < 5) return 2;   // cn role ttl now
    const std::string tok = harpia::session::issue(
        argv[1], argv[2], std::stoll(argv[3]), std::stoll(argv[4]));
    if (tok.empty()) return 3;
    harpia::session::Claims c;
    harpia::session::decode(tok, &c);
    std::printf("%s\t%s\n", tok.c_str(), c.jti.c_str());
    return 0;
}
'''


def _build_mint(g, tmp):
    src = os.path.join(tmp, "mint.cc")
    with open(src, "w") as f:
        f.write(_MINT_SRC)
    binp = os.path.join(tmp, "mint")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", os.path.join(g["cpp_root"], "http"),
         src, "-o", binp],
        capture_output=True, text=True, timeout=120)
    assert c.returncode == 0, "mint build failed:\n" + c.stderr
    return binp


def _mint(binp, cn, role, ttl, now):
    r = subprocess.run([binp, cn, role, str(ttl), str(now)],
                       capture_output=True, text=True,
                       env={**os.environ, "HARPIA_SESSION_KEY": SIGNING_KEY})
    assert r.returncode == 0, "mint run failed: " + r.stderr
    tok, jti = r.stdout.strip().split("\t")
    return tok, jti


@_http_toolchain
def test_rest_and_soap_sessions_over_mtls(generated):
    g = generated
    cpp_root = g["cpp_root"]
    proto = g["proto_dir"]
    pc = _pkgconfig("protobuf")
    mint = _build_mint(g, g["tmp"])

    prog = os.path.join(g["tmp"], "sess_https.cc")
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
    binary = os.path.join(g["tmp"], "sess_https")
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
        text=True, env=_server_env(g))

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

        def call(identity, method, path, body=None, headers=None):
            conn = http.client.HTTPSConnection("127.0.0.1", port,
                                               context=_client_ctx(g, identity),
                                               timeout=15)
            h = dict(headers or {})
            if body:
                h.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=body, headers=h)
            resp = conn.getresponse()
            out = (resp.status, resp.read().decode("utf-8", "replace"))
            conn.close()
            return out

        # ---- issue a token for admin via POST /v1/session ----
        st, txt = call("admin", "POST", "/v1/session")
        assert st == 200, (st, txt)
        m = re.search(r'"token"\s*:\s*"([^"]+)"', txt)
        assert m, txt
        admin_tok = m.group(1)

        # baseline (no token): guest cert may read, not write
        assert call("guest", "GET", "/v1/users")[0] == 200
        assert call("guest", "DELETE", "/v1/users/1")[0] == 403

        # the admin token, presented from the *guest* client cert, is gated on
        # the token's identity -> the admin verbs succeed
        bearer = {"Authorization": "Bearer " + admin_tok}
        assert call("guest", "GET", "/v1/users", headers=bearer)[0] == 200
        assert call("guest", "DELETE", "/v1/users/2", headers=bearer)[0] == 204
        assert call("guest", "GET", "/v1/users/2", headers=bearer)[0] == 404

        # a malformed / tampered token is refused outright (no fall-through to
        # the guest cert, which on GET would otherwise be a 200)
        assert call("guest", "GET", "/v1/users",
                    headers={"Authorization": "Bearer not.a.token"})[0] == 401
        tampered = admin_tok[:-1] + ("a" if admin_tok[-1] != "a" else "b")
        assert call("guest", "GET", "/v1/users",
                    headers={"Authorization": "Bearer " + tampered})[0] == 401

        # an already-expired token -> 401
        exp_tok, _ = _mint(mint, "admin", "admin", ttl=1, now=1000)
        assert call("guest", "GET", "/v1/users",
                    headers={"Authorization": "Bearer " + exp_tok})[0] == 401

        # a revoked token -> 401 (write its jti to the file the server watches)
        rev_tok, rev_jti = _mint(mint, "admin", "admin", ttl=3600,
                                 now=int(time.time()))
        assert call("guest", "GET", "/v1/users",
                    headers={"Authorization": "Bearer " + rev_tok})[0] == 200
        with open(g["revocations"], "w", encoding="utf-8") as fh:
            fh.write("# revoked\n{}\n".format(rev_jti))
        assert call("guest", "GET", "/v1/users",
                    headers={"Authorization": "Bearer " + rev_tok})[0] == 401
        with open(g["revocations"], "w", encoding="utf-8") as fh:
            fh.write("# cleared\n")

        # ---- SOAP: POST /soap/session mints a <sessionToken> envelope ----
        env = ('<soap:Envelope xmlns:soap='
               '"http://schemas.xmlsoap.org/soap/envelope/">')

        def soap(identity, path, xml, headers=None):
            conn = http.client.HTTPSConnection("127.0.0.1", port,
                                               context=_client_ctx(g, identity),
                                               timeout=15)
            h = {"Content-Type": "text/xml"}
            h.update(headers or {})
            conn.request("POST", path, body=xml, headers=h)
            resp = conn.getresponse()
            out = (resp.status, resp.read().decode("utf-8", "replace"))
            conn.close()
            return out

        st, txt = soap("admin", "/soap/session",
                       env + "<soap:Body><issueSession/></soap:Body></soap:Envelope>")
        assert st == 200 and "<sessionToken>" in txt, (st, txt)
        soap_tok = re.search(r"<sessionToken>([^<]+)</sessionToken>", txt).group(1)

        # a guest cert + the SOAP-issued admin token -> a create (set) succeeds
        set_body = (env + "<soap:Body><set><users><name>zion</name></users></set>"
                    "</soap:Body></soap:Envelope>")
        st, txt = soap("guest", "/soap/users", set_body)
        assert st == 403 and "Fault" in txt, (st, txt)          # no token: 403
        st, txt = soap("guest", "/soap/users", set_body,
                       headers={"Authorization": "Bearer " + soap_tok})
        assert st == 200 and "setResponse" in txt, (st, txt)    # token: allowed

        # no client cert at all -> refused at the TLS handshake
        bare = ssl.create_default_context(cafile=g["ca"])
        bare.check_hostname = False
        with pytest.raises((ssl.SSLError, ConnectionError, OSError)):
            nc = http.client.HTTPSConnection("127.0.0.1", port, context=bare,
                                             timeout=15)
            nc.request("POST", "/v1/session")
            nc.getresponse()
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


@_grpc_toolchain
def test_grpc_sessions_over_mtls(generated):
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

    prog = os.path.join(g["tmp"], "sess_grpc.cc")
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
            "using Stub = ::frameworkProtos::users_Service::Stub;\n"
            "static std::unique_ptr<Stub> mk(const std::string& a, const MtlsFiles& f) {{\n"
            "    return ::frameworkProtos::users_Service::NewStub(\n"
            "        ::grpc::CreateChannel(a, channel_credentials(true, f)));\n"
            "}}\n"
            "static ::grpc::StatusCode push_as(Stub* stub, int id,\n"
            "        const std::string& bearer) {{\n"
            "    ::frameworkProtos::users_Message req;\n"
            "    req.mutable_msg()->set_id_{h}(id);\n"
            '    req.mutable_msg()->set_name("n");\n'
            "    ::grpc::ClientContext c;\n"
            "    if (!bearer.empty()) c.AddMetadata(\"authorization\", \"Bearer \" + bearer);\n"
            "    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));\n"
            "    ::frameworkProtos::errorCode ec;\n"
            "    return stub->push(&c, req, &ec).error_code();\n"
            "}}\n"
            "// heartBeat with harpia-issue-session metadata -> a token in the\n"
            "// response trailing metadata.\n"
            "static std::string issue_via_heartbeat(Stub* stub) {{\n"
            "    ::frameworkProtos::users_HeartBeat hb;\n"
            "    ::frameworkProtos::users_HeartBeat out;\n"
            "    ::grpc::ClientContext c;\n"
            "    c.AddMetadata(\"harpia-issue-session\", \"1\");\n"
            "    c.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(8));\n"
            "    if (!stub->heartBeat(&c, hb, &out).ok()) return {{}};\n"
            "    const auto& md = c.GetServerTrailingMetadata();\n"
            "    auto it = md.find(\"harpia-session-token\");\n"
            "    if (it == md.end()) return {{}};\n"
            "    return std::string(it->second.data(), it->second.length());\n"
            "}}\n"
            "int main(int, char** argv) {{\n"
            "    const std::string addr = argv[1];\n"
            "    const std::string ca = argv[2], scrt = argv[3], skey = argv[4];\n"
            "    const std::string cdir = argv[5];\n"
            "    const std::string bad_tok = argv[6];\n"
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
            "    auto admin = mk(addr, cf(\"admin\"));\n"
            "    auto guest = mk(addr, cf(\"guest\"));\n"
            "    const std::string tok = issue_via_heartbeat(admin.get());\n"
            "    if (tok.empty()) rc = 10;\n"
            "    // guest cert, no token -> PERMISSION_DENIED\n"
            "    if (push_as(guest.get(), 1, \"\") != ::grpc::StatusCode::PERMISSION_DENIED) rc = 11;\n"
            "    // guest cert + the admin session token -> OK (token identity)\n"
            "    if (push_as(guest.get(), 2, tok) != ::grpc::StatusCode::OK) rc = 12;\n"
            "    // a bad token -> UNAUTHENTICATED (no fall-through to the cert)\n"
            "    if (push_as(admin.get(), 3, bad_tok) != ::grpc::StatusCode::UNAUTHENTICATED) rc = 13;\n"
            "    server.shutdown();\n"
            "    return rc;\n"
            "}}\n".format(h=HASH))

    objs = glob.glob(os.path.join(proto, "*.pb.cc"))
    binary = os.path.join(g["tmp"], "sess_grpc")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, *pc("--cflags"),
         prog, *objs, "-o", binary, "-lsoci_core", "-lsoci_sqlite3",
         *pc("--libs"), "-lssl", "-lcrypto", "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, "grpc sessions build failed:\n" + c.stderr

    run = subprocess.run([binary, addr, g["ca"], g["server_cert"],
                          g["server_key"], g["certs"], "v1.garbage.deadbeef"],
                         capture_output=True, text=True, timeout=90,
                         env=_server_env(g))
    assert run.returncode == 0, "grpc session check #{} (stderr={!r})".format(
        run.returncode, run.stderr)
