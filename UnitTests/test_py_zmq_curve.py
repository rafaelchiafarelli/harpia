"""python-target / py-zmq task 2: CURVE + the ZAP client-key allowlist
(``harpia_runtime.zmq`` CURVE options, ``harpia_runtime.zap``). Mirrors
``test_zmq_zap.py``.

Image-gated (pyzmq with CURVE), generated project (hardened repo profile, so
bind-side factories pass ``zap=True``):
- allowlist parsing: listed keys, identities, comment lines, a key that
  **starts with ``#``** kept (fixes/000005), a ``#`` identity ignored,
  missing file / unset env → empty;
- live ZAP over tcp: listed key accepted; unlisted key denied with exactly
  one value-free ``zap_denied`` record; a real key containing ``#`` accepted
  (fixes/000005; no real key can *start* with ``#``);
  missing allowlist file denies everyone;
- plain CURVE (``zap=False``): matching keys round-trip; a wrong server key
  times out and never falls back to plaintext;
- ``ensure_running`` is idempotent per context; a second handler on a
  context is inert; a factory refuses the wrong key type for its side.
g++ + cppzmq: a Python CURVE client against a generated C++ CURVE+ZAP
server reading the same allowlist file -- listed accepted, unlisted denied.
"""
import importlib
import os
import socket
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY or not P._importable("zmq"),
                                reason=P.SKIP_PY + " + pyzmq")

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_zmq_curve"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture()
def ctx():
    import zmq
    c = zmq.Context()
    yield c
    c.destroy(linger=0)


def _z():
    return importlib.import_module("harpia_generated.zmq.courier_{}_zmq".format(HASH))


def _rt():
    return importlib.import_module("harpia_runtime.zmq")


def _zap():
    return importlib.import_module("harpia_runtime.zap")


def _tcp():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "tcp://127.0.0.1:{}".format(port)


class Sink:
    def __init__(self):
        from harpia_runtime.compliance.audit_sink import AuditSink
        self.__class__ = type("Sink", (Sink, AuditSink), {})
        self.records = []

    def record(self, operation, subject, detail=""):
        self.records.append((operation, subject, detail))


def _hash_key(rt):
    """A real keypair whose public key contains '#' (the keys fixes/000005's
    cut-at-'#' parser denied). No real key can START with '#': the first Z85
    digit is floor(word / 85**4) <= 82 and '#' is digit 84."""
    for _ in range(5000):
        pub, sec = rt.generate_curve_keypair()
        if "#" in pub:
            return pub, sec
    pytest.fail("no key containing '#' in 5000 tries")


def test_allowlist_parsing(gen, tmp_path, monkeypatch):
    rt, zap = _rt(), _zap()
    a, _ = rt.generate_curve_keypair()
    b, _ = rt.generate_curve_keypair()
    h, _ = _hash_key(rt)
    lead = "#" + a[1:]  # a 40-char Z85 token starting with '#': a key, not a comment
    f = tmp_path / "allow.txt"
    f.write_text("\n".join([
        "# a comment line", "", "{} edge-01".format(a), "  {}   ".format(b),
        "{} #not-an-identity".format(h), "{} lead".format(lead),
        "#short-comment-token with words", ""]))
    al = zap.AllowList.from_file(str(f))
    assert al.contains(a) and al.contains(b) and al.contains(h) and al.contains(lead)
    assert al.identity(a) == "edge-01" and al.identity(b) == "" and al.identity(h) == ""
    assert al.identity(lead) == "lead"
    assert not al.contains("#short-comment-token") and not al.empty()
    assert zap.AllowList.from_file(str(tmp_path / "missing")).empty()
    monkeypatch.delenv(zap.ALLOWLIST_ENV, raising=False)
    assert zap.AllowList.from_env().empty()
    monkeypatch.setenv(zap.ALLOWLIST_ENV, str(f))
    assert zap.AllowList.from_env().contains(h)
    assert zap.is_z85_key(lead) and not zap.is_z85_key("#comment")


def _round(ctx, z, server_sec, server_pub, client_pub, client_sec, ms=1500):
    import zmq
    ep = _tcp()
    rx = z.new_receiver(ctx, ep, curve=_rt().CurveServerKeys(server_sec))
    rx.socket.setsockopt(zmq.RCVTIMEO, ms)
    tx = z.new_sender(ctx, ep, curve=_rt().CurveClientKeys(server_pub, client_pub, client_sec))
    m = z.courier()
    setattr(m, PK, 5)
    tx.send(m)
    got = rx.recv()
    tx.close()
    rx.close()
    return got


@pytest.fixture()
def keys(gen):
    rt = _rt()
    server = rt.generate_curve_keypair()
    good = rt.generate_curve_keypair()
    bad = rt.generate_curve_keypair()
    return server, good, bad


def test_zap_accepts_listed_denies_unlisted_and_audits(gen, ctx, keys, tmp_path, monkeypatch):
    (spub, ssec), (gpub, gsec), (bpub, bsec) = keys
    f = tmp_path / "allow.txt"
    f.write_text("{} edge-01\n".format(gpub))
    monkeypatch.setenv(_zap().ALLOWLIST_ENV, str(f))
    sink = Sink()
    handler = _zap().ensure_running(ctx, sink)
    assert handler.active() and _zap().ensure_running(ctx) is handler
    assert not _zap().ZapHandler(ctx).active()  # endpoint taken: inert
    z = _z()
    got = _round(ctx, z, ssec, spub, gpub, gsec)
    assert got is not None and getattr(got, PK) == 5
    assert sink.records == []
    assert _round(ctx, z, ssec, spub, bpub, bsec) is None
    denials = [r for r in sink.records if r[0] == "zap_denied"]
    assert denials and all(r == ("zap_denied", "inproc://zeromq.zap.01",
                                 "key={} mechanism=CURVE".format(bpub)) for r in denials)
    assert not any(bsec in a or ssec in a for r in sink.records for a in r)


def test_zap_key_containing_hash_accepted(gen, ctx, keys, tmp_path, monkeypatch):
    (spub, ssec), _, _ = keys
    hpub, hsec = _hash_key(_rt())
    f = tmp_path / "allow.txt"
    f.write_text("{} hash-key\n".format(hpub))
    monkeypatch.setenv(_zap().ALLOWLIST_ENV, str(f))
    got = _round(ctx, _z(), ssec, spub, hpub, hsec)
    assert got is not None and getattr(got, PK) == 5


def test_zap_missing_file_denies_all(gen, ctx, keys, tmp_path, monkeypatch):
    (spub, ssec), (gpub, gsec), _ = keys
    monkeypatch.setenv(_zap().ALLOWLIST_ENV, str(tmp_path / "does-not-exist"))
    assert _round(ctx, _z(), ssec, spub, gpub, gsec) is None


def test_plain_curve_and_wrong_server_key(gen, ctx, keys):
    import zmq
    rt = _rt()
    (spub, ssec), (gpub, gsec), (wrong, _) = keys
    msgs = P.fixture_messages(P.py_root(gen))

    def round_trip(server_pub):
        ep = _tcp()
        rx = rt.Receiver(ctx, ep, msgs["courier"], curve=rt.CurveServerKeys(ssec))
        rx.socket.setsockopt(zmq.RCVTIMEO, 1500)
        tx = rt.Sender(ctx, ep, "o", curve=rt.CurveClientKeys(server_pub, gpub, gsec))
        m = msgs["courier"]()
        setattr(m, PK, 6)
        tx.send(m)
        got = rx.recv()
        tx.close()
        rx.close()
        return got
    assert getattr(round_trip(spub), PK) == 6
    assert round_trip(wrong) is None  # handshake fails; never plaintext


def test_wrong_key_type_refused(gen, ctx):
    rt, z = _rt(), _z()
    with pytest.raises(TypeError):
        z.new_receiver(ctx, "inproc://x", curve=rt.CurveClientKeys("a", "b", "c"))
    with pytest.raises(TypeError):
        z.new_sender(ctx, "inproc://y", curve=rt.CurveServerKeys("a"))


_CPP = r'''
#include <cstdio>
#include "zmq/courier_%(h)s_zmq.h"
int main(int, char** argv) {
    ::zmq::context_t ctx;
    harpia::zmq_transport::courier_receiver r(ctx, argv[1],
        harpia::zmq_transport::CurveServerKeys{argv[2]});
    r.socket().set(::zmq::sockopt::rcvtimeo, 3000);
    std::printf("READY\n"); std::fflush(stdout);
    ::courier c;
    if (!r.recv(&c)) return 4;
    return c.id_%(h)s() == 5 ? 0 : 5;
}
'''


@pytest.fixture(scope="module")
def cpp_zap_server(gen, tmp_path_factory):
    import shutil
    if shutil.which("g++") is None or not os.path.exists("/usr/include/zmq.hpp"):
        pytest.skip("needs g++ + cppzmq")
    cpp_root = os.path.join(gen, "generated", "cpp")
    assert os.path.exists(os.path.join(cpp_root, "zap", "harpia_zap.h")), "not hardened"
    d = tmp_path_factory.mktemp("cpp_zap")
    (d / "s.cpp").write_text(_CPP % {"h": HASH})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf", "libzmq"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = d / "s"
    pb = os.path.join(cpp_root, "protofiles", "courier_{}.pb.cc".format(HASH))
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(d / "s.cpp"), pb,
                        "-o", str(exe), *flags, "-lpthread"],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    return str(exe)


@pytest.mark.parametrize("listed", [True, False])
def test_python_client_vs_cpp_zap_server(listed, gen, ctx, keys, cpp_zap_server, tmp_path):
    (spub, ssec), (gpub, gsec), (bpub, bsec) = keys
    f = tmp_path / "allow.txt"
    f.write_text("{} edge-01\n".format(gpub))
    ep = _tcp()
    env = dict(os.environ, HARPIA_ZMQ_ALLOWLIST=str(f))
    proc = subprocess.Popen([cpp_zap_server, ep, ssec], env=env, stdout=subprocess.PIPE,
                            text=True)
    assert proc.stdout.readline().strip() == "READY"
    pub, sec = (gpub, gsec) if listed else (bpub, bsec)
    tx = _z().new_sender(ctx, ep, curve=_rt().CurveClientKeys(spub, pub, sec))
    m = _z().courier()
    setattr(m, PK, 5)
    tx.send(m)
    assert proc.wait(timeout=30) == (0 if listed else 4)
    tx.close()
