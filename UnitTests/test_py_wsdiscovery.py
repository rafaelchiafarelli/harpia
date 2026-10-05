"""python-target / py-discovery task 1: the WS-Discovery responder
(``harpia_runtime.wsdiscovery``) + generated ``harpia_generated/sdc/*_sdc.py``.

- the descriptor set and each endpoint reference / scope / device type equal
  the C++ ``sdc/*_sdc.h`` (minted by ``SdcAdapter``'s code, imported);
- socket-free: a probe for ``dpws:Device`` matches every endpoint, a scope
  prefix filters, a resolve by reference answers one, an unrelated probe /
  unknown resolve / garbage / a DTD get nothing (no entity expansion);
- every answer is byte-identical to the C++ responder's for the same
  datagrams and SOAP URL [g++ + tinyxml2];
- live: the Python responder on a UDP port, probed and resolved by
  ``UnitTests/wsdiscovery_harness.py``'s client.
"""
import importlib
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
for p in (REPO_ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests import test_py_rbac as R  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)
HASH = R.HASH
gen = R.gen
SOAP = "http://127.0.0.1:8080/soap"


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


@pytest.fixture()
def use(gen):
    P.activate(P.py_root(gen))
    return gen


def _responder(names=("users", "patient_vitals")):
    r = _mod("harpia_runtime.wsdiscovery").Responder()
    for n in names:
        getattr(_mod("harpia_generated.sdc.%s_{h}_sdc" % n), "register_%s_wsdiscovery" % n)(
            r, SOAP)
    return r


def test_descriptors_match_cpp(use):
    cpp_dir = os.path.join(use, "generated", "cpp", "sdc")
    cpp = {f[:-len("_sdc.h")] for f in os.listdir(cpp_dir) if f.endswith("_sdc.h")}
    py = {f[:-len("_sdc.py")] for f in os.listdir(os.path.join(P.py_root(use),
                                                                "harpia_generated", "sdc"))
          if f.endswith("_sdc.py")}
    assert py == cpp and cpp
    for stem in cpp:
        header = open(os.path.join(cpp_dir, stem + "_sdc.h")).read()
        mod = importlib.import_module("harpia_generated.sdc.%s_sdc" % stem)
        assert re.search(r'endpoint_reference = "([^"]+)"', header).group(1) == \
            mod.ENDPOINT_REFERENCE
        assert re.search(r'ep.scopes = \{ "([^"]+)" \}', header).group(1) == mod.SCOPE
        assert re.search(r'ep.types = \{ "([^"]+)" \}', header).group(1) == mod.DEVICE_TYPE


def _probe(types="", scopes="", mid="urn:uuid:probe-1"):
    from wsdiscovery_harness import build_probe
    return build_probe(types=types.split() or None, scopes=scopes.split() or None,
                       message_id=mid)


def _resolve(epr, mid="urn:uuid:resolve-1"):
    from wsdiscovery_harness import build_resolve
    return build_resolve(epr, message_id=mid)


def datagrams():
    users = _mod("harpia_generated.sdc.users_{h}_sdc")
    return [
        ("probe-all", _probe()),
        ("probe-device", _probe("dpws:Device")),
        ("probe-scope", _probe(scopes=users.SCOPE)),
        ("probe-scope-prefix", _probe(scopes=users.SCOPE.rsplit("/", 1)[0])),
        ("probe-unrelated-type", _probe("foo:Bar")),
        ("probe-unrelated-scope", _probe(scopes="https://example.com/x")),
        ("resolve", _resolve(users.ENDPOINT_REFERENCE)),
        ("resolve-unknown", _resolve("urn:uuid:00000000-0000-0000-0000-000000000000")),
        ("garbage", b"not xml"),
        ("dtd", b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'),
        ("not-wsd", b'<soap:Envelope xmlns:soap="x"><soap:Body/></soap:Envelope>'),
    ]


def test_socket_free_answers(use):
    from wsdiscovery_harness import parse_matches
    r = _responder()
    got = {label: r.handle_datagram(d) for label, d in datagrams()}
    users = _mod("harpia_generated.sdc.users_{h}_sdc")
    for label in ("probe-unrelated-type", "probe-unrelated-scope", "resolve-unknown",
                  "garbage", "dtd", "not-wsd"):
        assert got[label] is None, label
    assert {m.scopes[0].rsplit("/", 1)[1] for m in parse_matches(got["probe-all"])} == \
        {"users", "patient_vitals"}
    assert got["probe-device"] == got["probe-all"]
    only = parse_matches(got["probe-scope"])
    assert [(m.endpoint_reference, m.xaddrs) for m in only] == \
        [(users.ENDPOINT_REFERENCE, [SOAP + "/users"])]
    assert len(parse_matches(got["probe-scope-prefix"])) == 2
    res = parse_matches(got["resolve"])
    assert len(res) == 1 and res[0].types == ["dpws:Device"]
    assert b"<wsa:RelatesTo>urn:uuid:resolve-1</wsa:RelatesTo>" in got["resolve"]


_CPP = r'''
#include <iostream>
#include <string>
#include "sdc/users_@H@_sdc.h"
#include "sdc/patient_vitals_@H@_sdc.h"
static std::string unhex(const std::string& h) {
    std::string out;
    for (size_t i = 0; i + 1 < h.size(); i += 2) out.push_back((char)std::stoi(h.substr(i, 2), nullptr, 16));
    return out;
}
static std::string hex(const std::string& s) {
    static const char* d = "0123456789abcdef"; std::string out;
    for (unsigned char c : s) { out.push_back(d[c >> 4]); out.push_back(d[c & 15]); }
    return out;
}
int main(int, char** argv) {
    harpia::wsdiscovery::Responder r;
    harpia::wsdiscovery::register_users_wsdiscovery(r, argv[1]);
    harpia::wsdiscovery::register_patient_vitals_wsdiscovery(r, argv[1]);
    std::string line;
    while (std::getline(std::cin, line)) {
        std::string out;
        std::cout << (r.handle_datagram(unhex(line), &out) ? hex(out) : "-") << "\n";
    }
    return 0;
}
'''


def test_byte_identical_to_cpp(use, tmp_path):
    tiny = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
    if shutil.which("g++") is None:
        pytest.skip("needs g++")
    (tmp_path / "w.cpp").write_text(_CPP.replace("@H@", HASH))
    c = subprocess.run(["g++", "-std=c++17", "-I", os.path.join(use, "generated", "cpp"),
                        "-I", tiny, str(tmp_path / "w.cpp"), os.path.join(tiny, "tinyxml2.cpp"),
                        "-o", str(tmp_path / "w")], capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr[-3000:]
    labels, grams = zip(*datagrams())
    out = subprocess.run([str(tmp_path / "w"), SOAP], input="".join(g.hex() + "\n" for g in grams),
                         capture_output=True, text=True, check=True, timeout=60).stdout.split()
    cpp = [None if o == "-" else bytes.fromhex(o) for o in out]
    r = _responder()
    py = [r.handle_datagram(g) for g in grams]
    assert dict(zip(labels, py)) == dict(zip(labels, cpp))


def test_live_probe_and_resolve(use):
    from wsdiscovery_harness import WSDiscoveryClient
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    r = _responder()
    assert r.start(port)
    try:
        with WSDiscoveryClient(timeout=4.0) as client:
            matches = client.probe(to_addr=("127.0.0.1", port))
        by = {m.scopes[0].rsplit("/", 1)[1]: m for m in matches}
        assert set(by) == {"users", "patient_vitals"}
        assert by["users"].xaddrs == [SOAP + "/users"]
        with WSDiscoveryClient(timeout=4.0) as client:
            resolved = client.resolve(by["users"].endpoint_reference,
                                      to_addr=("127.0.0.1", port))
        assert resolved.xaddrs == [SOAP + "/users"]
        t0 = time.monotonic()
        from wsdiscovery_harness import WSDiscoveryTimeout
        with WSDiscoveryClient(timeout=0.5) as client, pytest.raises(WSDiscoveryTimeout):
            client.probe(types=["foo:Bar"], to_addr=("127.0.0.1", port))
        assert time.monotonic() - t0 < 3
    finally:
        r.stop()
    assert r.start(port)  # restartable after stop
    r.stop()
