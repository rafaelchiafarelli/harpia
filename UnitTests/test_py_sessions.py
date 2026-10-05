"""python-target / py-transports-http task 7: bearer session tokens
(``harpia_runtime.session`` + ``.session_client`` + the RBAC gates'
bearer path + the issuance routes / ``heartBeat`` hook).

- primitives: SHA-256 (FIPS 180-4) and HMAC-SHA256 (RFC 4231) vectors,
  unpadded base64url both ways;
- the format is the contract: one corpus of tokens (valid, expired, revoked,
  tampered, spliced, malformed payloads of every getline/atoll shape) gives
  the same verdict, claims and ``session_denied`` text in Python and in
  ``harpia_session.h``, and tokens issued by either side verify on the other
  [g++];
- config: no key → no tokens (``no_key``), ``@file`` key, TTL, revocation
  re-read on content change both ways;
- generated mixed-mode ``HttpServer`` (hardened fixture): ``POST /session``
  (401 / 403 / 503 / token), a guest certificate + an admin token gets admin
  verbs (REST + SOAP), tampered / expired / revoked tokens are 401 and never
  fall through to the certificate; gRPC with client certs required issues
  from ``heartBeat`` and accepts the token; mixed-mode gRPC accepts an
  HTTPS-issued token from a certless channel;
- a token issued by the C++ ``HttpServer`` works on the Python one and the
  reverse [g++ + crow/asio + SOCI].
"""
import base64
import hashlib
import hmac
import importlib
import os
import shutil
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
from UnitTests import test_py_rbac as R  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY or shutil.which("openssl") is None,
                                reason=P.SKIP_PY + " + openssl")

HASH = R.HASH
KEY = "s3cret-session-key"
NOW = 1_700_000_000

gen = R.gen
pki = R.pki
role_map_file = R.role_map_file


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


@pytest.fixture()
def sess(gen, role_map_file, tmp_path, monkeypatch):
    """The generated project's session runtime with ``KEY`` configured, a
    revocation file at ``sess.revocations`` and every audit record in
    ``sess.records``."""
    P.activate(P.py_root(gen))
    R._arm(role_map_file, monkeypatch)
    rev = tmp_path / "revoked.txt"
    rev.write_text("")
    return _configure(monkeypatch, KEY, str(rev))


def _configure(monkeypatch, key, revocations="", ttl=None):
    for name, value in (("HARPIA_SESSION_KEY", key), ("HARPIA_SESSION_REVOCATIONS", revocations),
                        ("HARPIA_SESSION_TTL", ttl)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    mod = _mod("harpia_runtime.session")
    for attr in ("_KEY", "_TTL", "_REVOCATIONS"):
        monkeypatch.setattr(mod, attr, None)
    mod.records = _mod("harpia_runtime.rbac").records
    mod.revocations = revocations
    return mod


# -- primitives --------------------------------------------------------------------

def test_sha256_and_hmac_vectors(sess):
    assert hashlib.sha256(b"abc").hexdigest() == \
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    vectors = [  # RFC 4231 test cases 1, 2, 3, 4, 6, 7 (HMAC-SHA-256)
        (b"\x0b" * 20, b"Hi There",
         "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"),
        (b"Jefe", b"what do ya want for nothing?",
         "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
        (b"\xaa" * 20, b"\xdd" * 50,
         "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe"),
        (bytes(range(1, 26)), b"\xcd" * 50,
         "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b"),
        (b"\xaa" * 131, b"Test Using Larger Than Block-Size Key - Hash Key First",
         "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"),
        (b"\xaa" * 131, b"This is a test using a larger than block-size key and a larger "
         b"than block-size data. The key needs to be hashed before being used by the "
         b"HMAC algorithm.",
         "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2"),
    ]
    for key, msg, want in vectors:
        assert sess.hmac_sha256_hex(key, msg) == want


def test_b64url(sess):
    for n in range(0, 40):
        data = bytes((i * 37 + n) % 256 for i in range(n))
        enc = sess.b64url_encode(data)
        assert enc == base64.urlsafe_b64encode(data).decode().rstrip("=")
        assert sess.b64url_decode(enc) == data
    assert sess.b64url_decode("ab+c") is None and sess.b64url_decode("ab=") is None


# -- the format, Python vs C++ --------------------------------------------------------

def _sign(payload: bytes, key=KEY) -> str:
    b64 = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return "v1." + b64 + "." + hmac.new(key.encode(), b"harpiasess.v1." + b64.encode(),
                                        hashlib.sha256).hexdigest()


def corpus():
    good = _sign(b"admin\nadmin\n%d\n%d\nabc123" % (NOW - 10, NOW + 100))
    head, mac = good.rsplit(".", 1)
    other = _sign(b"guest\nguest\n%d\n%d\nzzz" % (NOW, NOW + 100))
    flipped = mac[:-1] + ("0" if mac[-1] != "0" else "1")
    return [
        good,
        _sign(b"admin\nadmin\n%d\n%d\nrevoked-jti" % (NOW, NOW + 100)),
        _sign(b"admin\nadmin\n%d\n%d\nold" % (NOW - 100, NOW)),          # exp == now
        _sign(b"admin\nadmin\n%d\n%d\nnext" % (NOW, NOW + 1)),
        _sign(b"a\nb\n1\n99999999999\n\n"),                              # empty jti line
        _sign(b"a\nb\n1\n99999999999\n"),                                # 4 lines
        _sign(b"a\nb\n1\n99999999999\nj\nextra\nlines"),
        _sign(b"a\nb\n 12x\n  +99999999999zz\nj"),                       # atoll prefixes
        _sign(b"a\nb\nabc\n-5\nj"),
        _sign(b"a\nb\n1\n99999999999999999999999\nj"),                   # saturates
        _sign(b"\nadmin\n1\n99999999999\nj"),                            # empty cn
        _sign(b""),
        _sign(b"admin\nadmin\n1\n99999999999\nj", key="other-key"),
        head + "." + flipped,
        head + "." + mac.upper(),
        other.rsplit(".", 1)[0] + "." + mac,                             # spliced body
        "v2." + good[3:], "v1.", "v1.abc", "v1.ab!c.deadbeef", "v1..x", "garbage", "",
        good + ".", "v1" + good[2:].replace(".", "", 1),
    ]


_CPP_TOKENS = r'''
#include <iostream>
#include <sstream>
#include <string>
#include "harpia_session.h"
using namespace harpia::session;
struct Cap : ::harpia::compliance::AuditSink {
    void record(const std::string& o, const std::string& s, const std::string& d) override {
        std::cout << "audit " << o << "|" << s << "|" << d << "\n";
    }
};
int main() {
    Cap cap;
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        std::string op; in >> op;
        if (op == "issue") {
            std::string cn, role; long long ttl, now; in >> cn >> role >> ttl >> now;
            std::cout << issue(cn, role, ttl, now) << "\n";
        } else {
            long long now; std::string tok; in >> now; std::getline(in, tok);
            if (!tok.empty() && tok[0] == ' ') tok.erase(0, 1);
            Claims c;
            Verdict v = verify(tok, &c, now, cap);
            std::cout << verdict_name(v) << " " << c.cn << "|" << c.role << "|" << c.jti
                      << "|" << c.issued_at << "|" << c.expires_at << "\n";
        }
        std::cout << "." << std::endl;
    }
    return 0;
}
'''


def _py_verify_lines(sess, token, now):
    lines = []
    sink_base = _mod("harpia_runtime.compliance.audit_sink").AuditSink

    class Printer(sink_base):
        def record(self, operation, subject, detail=""):
            lines.append("audit %s|%s|%s" % (operation, subject, detail))
    verdict, c = sess.verify(token, now, Printer())
    c = c or sess.Claims()
    lines.append("%s %s|%s|%s|%d|%d" % (verdict.value, c.cn, c.role, c.jti, c.issued_at,
                                       c.expires_at))
    return lines


@pytest.fixture(scope="module")
def cpp_tokens(tmp_path_factory):
    if shutil.which("g++") is None:
        pytest.skip("needs g++")
    d = tmp_path_factory.mktemp("session_cli")
    (d / "t.cpp").write_text(_CPP_TOKENS)
    c = subprocess.run(["g++", "-std=c++17", "-I", os.path.join(REPO_ROOT, "Compliance", "runtime"),
                        str(d / "t.cpp"), "-o", str(d / "t")], capture_output=True, text=True)
    assert c.returncode == 0, c.stderr
    return str(d / "t")


def _cpp_run(exe, requests, revocations):
    out = subprocess.run([exe], input="".join(r + "\n" for r in requests), capture_output=True,
                         text=True, check=True,
                         env={**os.environ, "HARPIA_SESSION_KEY": KEY,
                              "HARPIA_SESSION_REVOCATIONS": revocations}).stdout
    return [block.strip("\n").split("\n") if block.strip("\n") else []
            for block in out.split(".\n")[:-1]]


def test_same_verdicts_as_cpp(sess, cpp_tokens):
    with open(sess.revocations, "w") as f:
        f.write("# revoked\nrevoked-jti   # by ops\n")
    tokens = corpus()
    cpp = _cpp_run(cpp_tokens, ["verify %d %s" % (NOW, t) for t in tokens], sess.revocations)
    py = [_py_verify_lines(sess, t, NOW) for t in tokens]
    for token, p, c in zip(tokens, py, cpp):
        assert p == c, token
    verdicts = {line[-1].split(" ", 1)[0] for line in py}
    assert verdicts == {"ok", "malformed", "bad_signature", "expired", "revoked"}


def test_tokens_cross_verify(sess, cpp_tokens):
    issued_cpp = _cpp_run(cpp_tokens, ["issue admin admin 300 %d" % NOW,
                                       "issue guest guest 0 %d" % NOW], "")
    for (token,), (cn, ttl) in zip(issued_cpp, (("admin", 300), ("guest", 900))):
        verdict, claims = sess.verify(token, NOW + 1)
        assert verdict is sess.Verdict.ok
        assert (claims.cn, claims.role, claims.issued_at, claims.expires_at) == \
            (cn, cn, NOW, NOW + ttl)
        assert len(claims.jti) == 32
    py_tokens = [sess.issue("main", "main", 60, NOW), sess.issue("guest", "guest", 0, NOW)]
    cpp = _cpp_run(cpp_tokens, ["verify %d %s" % (NOW + 1, t) for t in py_tokens], "")
    assert [block[-1].split(" ")[0] for block in cpp] == ["ok", "ok"]
    assert cpp[0][-1].split(" ", 1)[1].startswith("main|main|")
    assert cpp[1][-1].endswith("|%d|%d" % (NOW, NOW + 900))


# -- configuration ------------------------------------------------------------------

def test_no_key_disables_sessions(sess, monkeypatch):
    s = _configure(monkeypatch, None)
    assert s.issue("admin", "admin") == ""
    assert s.verify(_sign(b"a\nb\n1\n99999999999\nj"))[0] is s.Verdict.no_key
    assert s.records == [("session_denied", "session", "verdict=no_key cn=<none> jti=<none>")]


def test_key_file_ttl_and_audit(sess, monkeypatch, tmp_path):
    (tmp_path / "k").write_bytes(KEY.encode() + b"\r\n")
    s = _configure(monkeypatch, "@" + str(tmp_path / "k"), ttl="42")
    tok = s.issue("admin", "admin", now=NOW)
    assert s.decode(tok).expires_at == NOW + 42
    assert tok.rsplit(".", 1)[1] == hmac.new(
        KEY.encode(), b"harpiasess.v1." + tok.split(".")[1].encode(), hashlib.sha256).hexdigest()
    assert s.issue("", "admin") == "" and s.issue("a\nb", "admin") == ""
    assert s.verify(tok, NOW + 42)[0] is s.Verdict.expired
    assert s.records[-1] == ("session_denied", "session", "verdict=expired cn=admin jti=%s"
                             % s.decode(tok).jti)
    assert all(tok.split(".")[1] not in r[2] for r in s.records)


def test_revocation_reloads_on_content_change(sess):
    tok = sess.issue("admin", "admin")
    jti = sess.decode(tok).jti
    assert sess.verify(tok)[0] is sess.Verdict.ok
    with open(sess.revocations, "w") as f:
        f.write(jti + "\n")
    assert sess.verify(tok)[0] is sess.Verdict.revoked
    with open(sess.revocations, "w") as f:
        f.write("# nothing revoked\n")
    assert sess.verify(tok)[0] is sess.Verdict.ok
    os.unlink(sess.revocations)
    assert sess.verify(tok)[0] is sess.Verdict.ok


def test_from_authorization(sess):
    tok = sess.issue("guest", "guest")
    for header in ("Bearer " + tok, "bearer " + tok, "BEARER  " + tok + " \r\n", tok):
        b = sess.from_authorization(header)
        assert (b.present, b.verdict, b.cn, b.role) == (True, sess.Verdict.ok, "guest", "guest")
    assert not sess.from_authorization("").present
    assert not sess.from_authorization("Bearer   ").present
    bad = sess.from_authorization("Bearer nope")
    assert bad.present and bad.verdict is sess.Verdict.malformed and bad.cn == ""


# -- generated servers ----------------------------------------------------------------

def _http(port, ctx, method, path, body=None, headers=None):
    return R._request(port, ctx, method, path, body, headers)


def _token_over_http(port, ctx, path="/v1/session"):
    status, body = _http(port, ctx, "POST", path)
    assert status == 200, body
    import json
    out = json.loads(body)
    assert out["token_type"] == "Bearer"
    return out["token"]


def test_http_issue_and_use(sess, pki, tmp_path):
    srv = R._py_http(pki, tmp_path)
    try:
        admin, guest = R._client_ctx(pki, "admin"), R._client_ctx(pki, "guest")
        assert _http(srv.port, R._client_ctx(pki, None), "POST", "/v1/session")[0] == 401
        assert _http(srv.port, R._client_ctx(pki, "stranger"), "POST", "/v1/session")[0] == 403
        status, body = _http(srv.port, R._client_ctx(pki, None), "POST", "/soap/session")
        assert status == 401 and "<faultstring>no client certificate</faultstring>" in body
        token = _token_over_http(srv.port, admin)
        status, body = _http(srv.port, guest, "POST", "/soap/session")
        assert status == 200 and body.startswith('<?xml version="1.0"?>') \
            and "<sessionToken>v1." in body
        sc = _mod("harpia_runtime.session_client")
        assert sc.http_session_token("https://localhost:%d/v1" % srv.port, guest).startswith("v1.")

        # the token, not the certificate, is the identity
        assert _http(srv.port, guest, "DELETE", "/v1/users/2")[0] == 403
        assert _http(srv.port, guest, "DELETE", "/v1/users/2",
                     headers=sc.bearer_header(token))[0] == 204
        soap_del = R._soap("<delete><id>1</id></delete>")
        xml = {"Content-Type": "text/xml", **sc.bearer_header(token)}
        status, body = _http(srv.port, guest, "POST", "/soap/users", soap_del, xml)
        assert status == 200 and "<ok>true</ok>" in body
        # and works with no certificate at all
        assert _http(srv.port, R._client_ctx(pki, None), "GET", "/v1/users",
                     headers=sc.bearer_header(token))[0] == 200

        # presented-but-invalid tokens never fall through to the admin cert
        expired = sess.issue("admin", "admin", ttl_seconds=5, now=NOW)
        revoked = sess.issue("admin", "admin")
        with open(sess.revocations, "w") as f:
            f.write(sess.decode(revoked).jti + "\n")
        tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
        before = len(sess.records)
        for bad in (tampered, expired, revoked, "garbage"):
            hdr = sc.bearer_header(bad)
            assert _http(srv.port, admin, "GET", "/v1/users", headers=hdr)[0] == 401
            status, body = _http(srv.port, admin, "POST", "/soap/users",
                                 R._soap("<get><id>1</id></get>"),
                                 {"Content-Type": "text/xml", **hdr})
            assert status == 401 and \
                "<faultcode>Client.Authentication</faultcode><faultstring>invalid session " \
                "token</faultstring>" in body
        denied = [r for r in sess.records[before:] if r[0] == "session_denied"]
        assert [d[2].split(" ")[0] for d in denied] == \
            ["verdict=bad_signature"] * 2 + ["verdict=expired"] * 2 + \
            ["verdict=revoked"] * 2 + ["verdict=malformed"] * 2
        assert not any(tampered.split(".")[1] in d[2] for d in denied)
        assert not [r for r in sess.records[before:] if r[0] == "rbac_denied"]
    finally:
        srv.stop()


def test_http_without_key_is_503(sess, pki, tmp_path, monkeypatch):
    _configure(monkeypatch, None)
    srv = R._py_http(pki, tmp_path)
    try:
        assert _http(srv.port, R._client_ctx(pki, "admin"), "POST", "/v1/session")[0] == 503
        status, body = _http(srv.port, R._client_ctx(pki, "admin"), "POST", "/soap/session")
        assert status == 503 and "sessions not configured" in body
    finally:
        srv.stop()


def test_grpc_heartbeat_issue_and_use(sess, pki, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    import grpc
    tls = _mod("harpia_runtime.tls")
    sc = _mod("harpia_runtime.session_client")
    mod = _mod("harpia_generated.grpc.users_{h}_grpc")
    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    mod.add_to_server(mod.users_Service(R._grpc_pool(tmp_path)), server)
    port = server.add_secure_port("localhost:0", tls.grpc_server_credentials(
        True, tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]), True))
    server.start()

    def channel(who):
        return grpc.secure_channel("localhost:%d" % port, tls.grpc_channel_credentials(
            tls.MtlsFiles(pki["ca"], *pki[who])))
    stub_mod = _mod("harpia_generated.protofiles.users_{h}_service_pb2_grpc")
    svc = R._grpc_svc()
    try:
        ch = channel("admin")
        token = sc.grpc_session_token(stub_mod.users_ServiceStub(ch).heartBeat,
                                      svc.users_HeartBeat())
        assert sess.decode(token).cn == "admin"
        hb, call = stub_mod.users_ServiceStub(ch).heartBeat.with_call(svc.users_HeartBeat())
        assert not dict(call.trailing_metadata() or ())  # only when asked
        ch.close()
        ch = channel("guest")
        stub = stub_mod.users_ServiceStub(ch)
        push = svc.users_Message()
        setattr(push.msg, R.PK, 77)
        with pytest.raises(grpc.RpcError) as e:
            stub.push(push)
        assert e.value.code() == grpc.StatusCode.PERMISSION_DENIED
        assert stub.push(push, metadata=sc.bearer_metadata(token)).code == 0
        with pytest.raises(grpc.RpcError) as e:
            stub.pullByID(svc.users_ID(id=1), metadata=sc.bearer_metadata(
                token[:-1] + ("0" if token[-1] != "0" else "1")))
        assert (e.value.code(), e.value.details()) == \
            (grpc.StatusCode.UNAUTHENTICATED, "invalid session token")
        ch.close()
    finally:
        server.stop(None).wait()


def test_grpc_mixed_mode_accepts_https_token(sess, pki, tmp_path):
    import grpc
    tls = _mod("harpia_runtime.tls")
    sc = _mod("harpia_runtime.session_client")
    http = R._py_http(pki, tmp_path)
    srv = _mod("harpia_generated.grpc.grpc_server_bringup").GrpcServer(
        R._grpc_pool(tmp_path), "localhost:0",
        mtls=tls.MtlsFiles(pki["ca"], pki["cert"], pki["key"]))
    srv.start()
    try:
        token = sc.http_session_token("https://localhost:%d/v1" % http.port,
                                      R._client_ctx(pki, "main"))
        ch = grpc.secure_channel("localhost:%d" % srv.port, grpc.ssl_channel_credentials(
            root_certificates=open(pki["ca"], "rb").read()))
        stub = _mod("harpia_generated.protofiles.users_{h}_service_pb2_grpc").users_ServiceStub(ch)
        svc = R._grpc_svc()
        try:
            got = stub.pullByID(svc.users_ID(id=1), metadata=sc.bearer_metadata(token))
            assert got.msg.name == "neo"
            with pytest.raises(sc.SessionUnavailable):  # no client cert seen in mixed mode
                sc.grpc_session_token(stub.heartBeat, svc.users_HeartBeat())
        finally:
            ch.close()
    finally:
        srv.stop()
        http.stop()


@pytest.mark.skipif(not R.HAVE_CPP_HTTP, reason="needs g++ + pkg-config + vendored crow/asio")
def test_tokens_cross_cpp_and_python_servers(sess, gen, pki, role_map_file, tmp_path):
    exe = R.build_cpp_http(gen, tmp_path)
    env = {"HARPIA_RBAC_MAP": role_map_file, "HARPIA_SESSION_KEY": KEY,
           "HARPIA_SESSION_REVOCATIONS": sess.revocations}
    srv = R._py_http(pki, tmp_path)
    guest, admin = R._client_ctx(pki, "guest"), R._client_ctx(pki, "admin")
    sc = _mod("harpia_runtime.session_client")
    try:
        with R.running_cpp_http(exe, pki, env) as cpp_port:
            cpp_token = _token_over_http(cpp_port, admin)
            py_token = _token_over_http(srv.port, admin)
            for port in (cpp_port, srv.port):
                for token in (cpp_token, py_token):
                    hdr = sc.bearer_header(token)
                    assert _http(port, guest, "DELETE", "/v1/users/2", headers=hdr)[0] == 204
                    assert _http(port, guest, "GET", "/v1/users",
                                 headers=sc.bearer_header(token[:-1] + "x"))[0] == 401
            assert sess.verify(cpp_token)[1].cn == "admin"
    finally:
        srv.stop()
