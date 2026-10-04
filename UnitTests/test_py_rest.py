"""python-target / py-transports-http task 2: generated REST CRUD
(``harpia_generated/rest/*_rest.py`` over ``harpia_runtime.http.rest`` /
``.router``) registered on a plaintext ``harpia_runtime.http.router.Server`` (the
bring-up needs mTLS here: the fixture has ``protected`` messages).

Generated under a low-risk profile (``class_a`` / ``standalone``), so every
route uses the flat ``X-User`` / ``X-Pswd`` gate. Image-gated:
- 401 without / with wrong credentials (before any DB work);
- POST (JSON and XML bodies) → 201, GET item (JSON and XML by ``Accept``),
  PUT → 204, DELETE → 204, GET missing → 404, unparsable body → 400,
  duplicate key → 500; PUT / DELETE of a missing row → 204 (as C++);
- list as JSON ``[...]`` / XML ``<list>...</list>``; ``?limit=&offset=``
  paging; every ``DEFAULT_LIMIT`` equals the C++ one, and a default page
  size applies when ``?limit`` is absent;
- unknown path 404, wrong method 405, an oversized body 413;
- pool of 1 with its connection held → 503 ``db pool exhausted``;
- the module set equals the C++ ``rest/*_rest.h`` set.
g++: the C++ test client (``harpia_test_client.h``) drives the Python
server through create / page / read / update / delete / 401.
"""
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

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
CRED = {"X-User": "users", "X-Pswd": HASH}


def generate_low_risk(tmp):
    """The HarpiaTest fixture generated for Python under a low-risk profile
    (flat gates)."""
    cfg = os.path.join(str(tmp), "low_risk.harpia.yaml")
    with open(cfg, "w") as f:
        f.write("risk_class: class_a\ntopology: standalone\n")
    old = os.environ.get("HARPIA_COMPLIANCE_CONFIG")
    os.environ["HARPIA_COMPLIANCE_CONFIG"] = cfg
    try:
        return P.generate_python(os.path.join(str(tmp), "out"))
    finally:
        if old is None:
            os.environ.pop("HARPIA_COMPLIANCE_CONFIG")
        else:
            os.environ["HARPIA_COMPLIANCE_CONFIG"] = old


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("py_rest")
    os.makedirs(os.path.join(str(tmp), "out"))
    g = generate_low_risk(tmp)
    P.fixture_messages(P.py_root(g))
    return g


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


@pytest.fixture()
def server(gen, tmp_path):
    pool_mod = _mod("harpia_runtime.db.pool")
    pool = pool_mod.sqlite_pool(str(tmp_path / "rest.db"), size=4)
    with pool.borrow() as conn:
        for name in ("users", "data"):
            getattr(_mod("harpia_generated.db.%s_{h}_dao" % name), name + "_dao")(
                conn).create_table()
    srv = plain_http(pool, rest_base="/api/v1")
    yield srv, pool
    srv.stop()


def plain_http(pool, rest_base="", soap_base="/soap", names=("users", "data")):
    """``names``' REST + SOAP routes on a plaintext server. Not the generated
    ``HttpServer``: the fixture's ``protected`` messages make its bring-up
    require mTLS (``EMIT_TLS``) even under a low-risk profile -- as the C++
    tests, register the bindings directly (the bring-up has its own mTLS test)."""
    router_mod = _mod("harpia_runtime.http.router")
    router = router_mod.Router()
    for name in names:
        _mod("harpia_generated.rest.%s_{h}_rest" % name).register(router, pool, rest_base)
        _mod("harpia_generated.soap.%s_{h}_soap" % name).register(router, pool, soap_base)
    srv = router_mod.Server(router)
    srv.start()
    return srv


def call(srv, method, path, body=None, headers=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (srv.port, path), data=body,
                                 method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


def _user(pk, name):
    m = _mod("harpia_generated.protofiles.users_{h}_pb2").users()
    setattr(m, PK, pk)
    m.name = name
    return m


def _json(m):
    return _mod("harpia_runtime.json").to_json(m).encode()


def test_module_set_matches_cpp(gen):
    cpp = {f[:-len("_rest.h")] for f in os.listdir(os.path.join(gen, "generated", "cpp", "rest"))
           if f.endswith("_rest.h")}
    py = {f[:-len("_rest.py")] for f in os.listdir(os.path.join(P.py_root(gen), "harpia_generated",
                                                                 "rest")) if f.endswith("_rest.py")}
    assert py == cpp and cpp


def test_flat_gate(server):
    srv, _ = server
    assert call(srv, "GET", "/api/v1/users")[0] == 401
    assert call(srv, "GET", "/api/v1/users", headers={"X-User": "users", "X-Pswd": "x"})[0] == 401
    assert call(srv, "GET", "/api/v1/users", headers={"X-User": "data", "X-Pswd": HASH})[0] == 401
    assert call(srv, "GET", "/api/v1/users", headers=CRED)[0] == 200


def test_crud_both_content_types(server):
    srv, _ = server
    xml = _mod("harpia_runtime.xml")
    users = _mod("harpia_generated.protofiles.users_{h}_pb2").users
    json_h = dict(CRED, **{"Content-Type": "application/json"})
    xml_h = dict(CRED, **{"Content-Type": "application/xml"})
    assert call(srv, "POST", "/api/v1/users", _json(_user(1, "neo")), json_h)[0] == 201
    assert call(srv, "POST", "/api/v1/users", xml.to_xml(_user(2, "trinity")).encode(),
                xml_h)[0] == 201
    status, body, ctype = call(srv, "GET", "/api/v1/users/1", headers=CRED)
    got = users()
    assert status == 200 and ctype == "application/json"
    assert _mod("harpia_runtime.json").from_json(body.decode(), got) and got.name == "neo"
    status, body, ctype = call(srv, "GET", "/api/v1/users/2",
                               headers=dict(CRED, Accept="application/xml"))
    got = users()
    assert status == 200 and ctype == "application/xml"
    assert xml.from_xml(body.decode(), got) and got.name == "trinity"
    assert call(srv, "PUT", "/api/v1/users/1", _json(_user(1, "thomas")), json_h)[0] == 204
    assert b"thomas" in call(srv, "GET", "/api/v1/users/1", headers=CRED)[1]
    assert call(srv, "DELETE", "/api/v1/users/1", headers=CRED)[0] == 204
    assert call(srv, "GET", "/api/v1/users/1", headers=CRED)[0] == 404
    assert call(srv, "POST", "/api/v1/users", b"{not json", json_h)[0] == 400
    assert call(srv, "POST", "/api/v1/users", _json(_user(2, "dup")), json_h)[0] == 500
    assert call(srv, "PUT", "/api/v1/users/77", _json(_user(77, "ghost")), json_h)[0] == 204
    assert call(srv, "DELETE", "/api/v1/users/77", headers=CRED)[0] == 204


def test_list_and_pagination(server):
    srv, _ = server
    json_h = dict(CRED, **{"Content-Type": "application/json"})
    for i in range(1, 6):
        call(srv, "POST", "/api/v1/users", _json(_user(i, "n%d" % i)), json_h)
    status, body, ctype = call(srv, "GET", "/api/v1/users", headers=CRED)
    assert status == 200 and ctype == "application/json"
    assert body.startswith(b"[") and all(b'"n%d"' % i in body for i in range(1, 6))
    page = call(srv, "GET", "/api/v1/users?limit=2&offset=1", headers=CRED)[1]
    assert b'"n2"' in page and b'"n3"' in page and b'"n1"' not in page and b'"n4"' not in page
    status, body, ctype = call(srv, "GET", "/api/v1/users",
                               headers=dict(CRED, Accept="application/xml"))
    assert ctype == "application/xml" and body.startswith(b"<list>") and body.endswith(b"</list>")


def test_default_limits_match_cpp_and_apply(gen, tmp_path):
    import re
    cpp_dir = os.path.join(gen, "generated", "cpp", "rest")
    for f in os.listdir(cpp_dir):
        want = int(re.search(r"std::atoll\(lim_s\) : (\d+)LL", open(os.path.join(cpp_dir, f))
                             .read()).group(1))
        name = f[:-len("_{}_rest.h".format(HASH))]
        assert _mod("harpia_generated.rest.%s_{h}_rest" % name).DEFAULT_LIMIT == want
    # no fixture table declares pagination[size]; exercise a default of 2
    router_mod, rest = _mod("harpia_runtime.http.router"), _mod("harpia_runtime.http.rest")
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "d.db"), size=2)
    dao = _mod("harpia_generated.db.users_{h}_dao").users_dao
    with pool.borrow() as conn:
        dao(conn).create_table()
        for i in range(1, 6):
            dao(conn).create(_user(i, "n%d" % i))
    router = router_mod.Router()
    rest.register_crud(router, pool, "", "users", dao,
                       _mod("harpia_generated.protofiles.users_{h}_pb2").users,
                       rest.flat_gate("users", HASH), default_limit=2)
    srv = router_mod.Server(router)
    srv.start()
    try:
        body = call(srv, "GET", "/users", headers=CRED)[1]
        assert body.count(b'"name"') == 2 and b'"n1"' in body and b'"n2"' in body
        assert call(srv, "GET", "/users?limit=0", headers=CRED)[1].count(b'"name"') == 5
    finally:
        srv.stop()


def test_router_errors(server):
    srv, _ = server
    assert call(srv, "GET", "/api/v1/nope", headers=CRED)[0] == 404
    assert call(srv, "POST", "/api/v1/users/1", b"{}", CRED)[0] == 405
    import socket
    with socket.create_connection(("127.0.0.1", srv.port), timeout=10) as sk:
        # declare an oversized body, send none: the server refuses up front
        sk.sendall(b"POST /api/v1/users HTTP/1.1\r\nHost: x\r\nX-User: users\r\n"
                   b"Content-Length: %d\r\n\r\n" % ((1 << 20) + 1))
        assert sk.recv(64).startswith(b"HTTP/1.1 413")


def test_pool_exhausted_is_503(gen, tmp_path):
    pool_mod = _mod("harpia_runtime.db.pool")
    pool = pool_mod.sqlite_pool(str(tmp_path / "x.db"), size=1, borrow_timeout_s=0.2)
    srv = plain_http(pool)
    try:
        with pool.borrow():
            status, body, _ = call(srv, "GET", "/users", headers=CRED)
        assert (status, body) == (503, b"db pool exhausted")
        assert call(srv, "GET", "/users", headers={})[0] == 401  # gate before borrow
    finally:
        srv.stop()


_CPP = r'''
#include <cstdio>
#include <string>
#include "harpia_test_client.h"
int main(int argc, char** argv) {
    harpia_test::Client cli("127.0.0.1", std::stoi(argv[1]));
    const std::string h = argv[2];
    cli.set_default_headers({{"X-User", "users"}, {"X-Pswd", h}});
    for (int i = 3; i < 8; ++i) {
        auto r = cli.Post("/api/v1/users", argv[i], "application/json");
        std::printf("post %d\n", r.status);
    }
    auto page = cli.Get("/api/v1/users?limit=2&offset=1");
    std::printf("page %d %s\n", page.status, page.body.c_str());
    auto one = cli.Get("/api/v1/users/3");
    std::printf("get %d %s\n", one.status, one.body.c_str());
    std::printf("put %d\n", cli.Put("/api/v1/users/3", argv[8], "application/json").status);
    std::printf("del %d\n", cli.Delete("/api/v1/users/3").status);
    std::printf("gone %d\n", cli.Get("/api/v1/users/3").status);
    harpia_test::Client anon("127.0.0.1", std::stoi(argv[1]));
    std::printf("anon %d\n", anon.Get("/api/v1/users").status);
    return 0;
}
'''


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_cpp_client_drives_python_server(server, tmp_path):
    srv, _ = server
    (tmp_path / "c.cpp").write_text(_CPP)
    exe = tmp_path / "c"
    c = subprocess.run(["g++", "-std=c++17", "-I", HERE, str(tmp_path / "c.cpp"), "-o", str(exe)],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    bodies = [_json(_user(i, "n%d" % i)).decode() for i in range(1, 6)]
    out = subprocess.run([str(exe), str(srv.port), HASH, *bodies,
                          _json(_user(3, "changed")).decode()],
                         capture_output=True, text=True, timeout=60, check=True).stdout
    lines = out.splitlines()
    assert lines[:5] == ["post 201"] * 5
    assert lines[5].startswith("page 200 [") and '"n2"' in lines[5] and '"n4"' not in lines[5]
    assert lines[6].startswith("get 200 ") and '"n3"' in lines[6]
    assert lines[7:] == ["put 204", "del 204", "gone 404", "anon 401"]
