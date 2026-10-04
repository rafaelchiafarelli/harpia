"""python-target / py-transports-http task 3: the SOAP endpoint
(``harpia_runtime.soap`` seam + ``harpia_runtime.http.soap_endpoint`` +
generated ``harpia_generated/soap/*_soap.py``), on a plaintext router
(see ``test_py_rest.plain_http``).

Generated under a low-risk profile (flat ``<credentials>`` gate):
- the module set equals the C++ ``soap/*_soap.h`` set, each pointing at its
  ``wsdl/<name>_<hash>.wsdl`` (which exists);
- every operation and status code: 400 malformed / empty Body / undecodable
  message element, 401 Fault (bad / missing credentials, before any DB work),
  200 ``set``/``update``/``delete`` ``<ok>``, ``get`` response, 200 "not found"
  and "unknown operation" Faults, 503 Fault when the pool is exhausted;
- a document with a DTD is refused (400) and a billion-laughs payload never
  expands;
- fuzz: 3000 mutated envelopes through ``message_from_request`` return a
  bool, never raise, each well under a second.
g++ + Crow: the same ordered request sequence (incl. an undeclared namespace
prefix, which tinyxml2 accepts) against the C++ endpoint and the Python one
gives identical status codes and identical response envelopes.
"""
import importlib
import os
import random
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests.test_py_rest import generate_low_risk, plain_http  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
ENV = '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
HDR = ("<soap:Header><credentials><user>users</user><pswd>%s</pswd></credentials>"
       "</soap:Header>" % HASH)
BAD = ("<soap:Header><credentials><user>users</user><pswd>wrong</pswd></credentials>"
       "</soap:Header>")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("py_soap")
    os.makedirs(os.path.join(str(tmp), "out"))
    g = generate_low_risk(tmp)
    P.fixture_messages(P.py_root(g))
    return g


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


def _py_server(tmp_path, size=4, timeout=5.0):
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "soap.db"), size=size,
                                                       borrow_timeout_s=timeout)
    with pool.borrow() as conn:
        _mod("harpia_generated.db.users_{h}_dao").users_dao(conn).create_table()
    return plain_http(pool, names=("users",)), pool


def post(port, body, path="/soap/users"):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                 data=body.encode() if isinstance(body, str) else body,
                                 method="POST", headers={"Content-Type": "text/xml"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _user_xml(pk, name):
    m = _mod("harpia_generated.protofiles.users_{h}_pb2").users()
    setattr(m, PK, pk)
    m.name = name
    return _mod("harpia_runtime.xml").to_xml(m)


def _env(body, hdr=HDR):
    return ENV + hdr + "<soap:Body>" + body + "</soap:Body></soap:Envelope>"


def sequence():
    """(label, envelope) -- ordered; state carries between steps."""
    return [
        ("garbage", "this is not xml"),
        ("bad-cred", _env("<set>" + _user_xml(1, "neo") + "</set>", BAD)),
        ("no-cred", _env("<set>" + _user_xml(1, "neo") + "</set>", "")),
        ("empty-body", _env("")),
        ("set", _env("<set>" + _user_xml(1, "neo") + "</set>")),
        ("set-dup", _env("<set>" + _user_xml(1, "again") + "</set>")),
        ("get", _env("<get><id>1</id></get>")),
        ("get-missing", _env("<get><id>999</id></get>")),
        ("update", _env("<update>" + _user_xml(1, "thomas") + "</update>")),
        ("get-updated", _env("<get><id>1</id></get>")),
        ("update-missing", _env("<update>" + _user_xml(42, "ghost") + "</update>")),
        ("set-empty", _env("<set></set>")),
        ("unknown-op", _env("<frobnicate/>")),
        ("undeclared-prefix", "<s:Envelope>" + HDR.replace("soap:", "s:")
         + "<s:Body><get><id>1</id></get></s:Body></s:Envelope>"),
        ("delete", _env("<delete><id>1</id></delete>")),
        ("get-deleted", _env("<get><id>1</id></get>")),
    ]


def test_module_set_and_wsdl(gen):
    cpp = {f[:-len("_soap.h")] for f in os.listdir(os.path.join(gen, "generated", "cpp", "soap"))
           if f.endswith("_soap.h") and f != "harpia_soap.h"}
    py_dir = os.path.join(P.py_root(gen), "harpia_generated", "soap")
    py = {f[:-len("_soap.py")] for f in os.listdir(py_dir) if f.endswith("_soap.py")}
    assert py == cpp and cpp
    for stem in py:
        wsdl = importlib.import_module("harpia_generated.soap.%s_soap" % stem).WSDL
        assert os.path.exists(os.path.join(gen, wsdl)), wsdl


def test_operations_and_status_codes(gen, tmp_path):
    srv, _ = _py_server(tmp_path)
    try:
        got = {label: post(srv.port, body) for label, body in sequence()}
    finally:
        srv.stop()
    assert got["garbage"] == (400, "")
    for label in ("bad-cred", "no-cred"):
        assert got[label][0] == 401 and "Client.Authentication" in got[label][1]
    assert got["empty-body"][0] == 400 and got["set-empty"][0] == 400
    assert got["set"] == (200, _mod("harpia_runtime.soap").envelope(
        "<setResponse><ok>true</ok></setResponse>"))
    assert "<ok>false</ok>" in got["set-dup"][1]
    assert got["get"][0] == 200 and "<getResponse>" in got["get"][1] and "neo" in got["get"][1]
    assert "not found" in got["get-missing"][1] and got["get-missing"][0] == 200
    assert "thomas" in got["get-updated"][1]
    assert "<ok>true</ok>" in got["update-missing"][1]
    assert got["unknown-op"][0] == 200 and "unknown operation" in got["unknown-op"][1]
    assert got["undeclared-prefix"][0] == 200 and "thomas" in got["undeclared-prefix"][1]
    assert "<deleteResponse><ok>true</ok>" in got["delete"][1]
    assert "not found" in got["get-deleted"][1]


def test_pool_exhausted_503(gen, tmp_path):
    srv, pool = _py_server(tmp_path, size=1, timeout=0.2)
    try:
        with pool.borrow():
            status, body = post(srv.port, _env("<get><id>1</id></get>"))
        assert status == 503 and "db pool exhausted" in body
    finally:
        srv.stop()


def test_dtd_refused_and_no_entity_expansion(gen, tmp_path):
    soap = _mod("harpia_runtime.soap")
    lol = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
           + "".join('<!ENTITY lol%d "%s">' % (i, ("&lol%d;" % (i - 1) if i else "&lol;") * 10)
                     for i in range(1, 10))
           + ']>' + ENV + HDR + "<soap:Body><get><id>&lol9;</id></get></soap:Body></soap:Envelope>")
    t0 = time.monotonic()
    assert soap.parse_envelope(lol) is None
    assert time.monotonic() - t0 < 0.5
    srv, _ = _py_server(tmp_path)
    try:
        assert post(srv.port, lol)[0] == 400
    finally:
        srv.stop()


def test_fuzz_message_from_request(gen):
    soap = _mod("harpia_runtime.soap")
    users = _mod("harpia_generated.protofiles.users_{h}_pb2").users
    seed = _env("<set>" + _user_xml(7, "fuzz<&>") + "</set>").encode()
    rng = random.Random(1234)
    alphabet = b"<>/=\"' &;:!?[]abcxyz0123456789\x00\xff"
    worst = 0.0
    for _ in range(3000):
        data = bytearray(seed)
        for _ in range(rng.randint(1, 8)):
            op = rng.random()
            pos = rng.randrange(len(data) + 1)
            if op < 0.4 and data:
                del data[min(pos, len(data) - 1)]
            elif op < 0.8:
                data.insert(pos, rng.choice(alphabet))
            else:
                data[pos:pos] = data[rng.randrange(len(data)):][:rng.randint(1, 40)]
        t0 = time.monotonic()
        result = soap.message_from_request(bytes(data), users())
        worst = max(worst, time.monotonic() - t0)
        assert result in (True, False)
    assert worst < 1.0
    assert soap.message_from_request(seed, users()) is True


_CPP = r'''
#include <cstdio>
#include <iostream>
#include <string>
#include "soap/users_%(h)s_soap.h"
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
int main(int, char** argv) {
    ::soci::session db(::soci::sqlite3, argv[2]);
    harpia::db::users_dao dao(db);
    if (!dao.create_table()) return 2;
    crow::SimpleApp app;
    app.loglevel(crow::LogLevel::Warning);
    harpia::soap::register_users_soap(app, db, "/soap");
    auto fut = app.bindaddr("127.0.0.1").port(std::stoi(argv[1])).multithreaded().run_async();
    app.wait_for_server_start();
    std::printf("READY\n"); std::fflush(stdout);
    std::string line; std::getline(std::cin, line);   // until stdin closes
    app.stop(); fut.get();
    return 0;
}
'''


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.skipif(shutil.which("g++") is None or shutil.which("pkg-config") is None,
                    reason="needs g++ + protobuf + SOCI")
def test_same_envelopes_as_cpp(gen, tmp_path):
    cpp_root = os.path.join(gen, "generated", "cpp")
    third = os.path.join(REPO_ROOT, "third_party")
    (tmp_path / "s.cpp").write_text(_CPP % {"h": HASH})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "s"
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, "-I", os.path.join(third, "crow"),
         "-I", os.path.join(third, "asio"), "-I", os.path.join(third, "tinyxml2"),
         str(tmp_path / "s.cpp"), os.path.join(cpp_root, "protofiles",
                                               "users_{}.pb.cc".format(HASH)),
         os.path.join(third, "tinyxml2", "tinyxml2.cpp"), "-o", str(exe),
         "-lsoci_core", "-lsoci_sqlite3", *flags, "-lpthread", "-ldl"],
        capture_output=True, text=True, timeout=600)
    assert c.returncode == 0, c.stderr
    port = _free_port()
    proc = subprocess.Popen([str(exe), str(port), str(tmp_path / "cpp.db")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "READY"
        cpp = [(label, post(port, body)) for label, body in sequence()]
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)
    srv, _ = _py_server(tmp_path)
    try:
        py = [(label, post(srv.port, body)) for label, body in sequence()]
    finally:
        srv.stop()
    # Crow fills a bodyless error response with its status line
    # ("400 Bad Request\r\n"); that is Crow's, not part of the envelope
    # contract -- compare those as empty, everything else byte for byte.
    import re
    crow_default = re.compile(r"\d{3} [A-Za-z ]+\r\n")
    cpp = [(label, (status, "" if crow_default.fullmatch(body) else body))
           for label, (status, body) in cpp]
    assert py == cpp
