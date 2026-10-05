"""python-target / py-zmq task 1: ``harpia_runtime.zmq`` + generated
``harpia_generated/zmq/<name>_<hash>_zmq.py``.

Structural (generated project): one module per C++ ``zmq/*_zmq.h``, the
factories its roles call for, and ``ORIGIN_ID`` equal to the C++
``origin_id()`` string.
Image-gated (pyzmq): PUSH/PULL and PUB/SUB round trips over inproc and tcp;
one-to-* senders stamp ``ORIGIN_ID``, many-to-* senders a distinct
``runtime_origin_id()`` each; a garbage frame reads as ``None``; N-peer
fan-out (every subscriber gets every message) and PUSH/PULL load-balance
(each message exactly once across pullers).
g++ + cppzmq: a generated C++ ``courier_sender`` pushes to a Python
``new_receiver`` over tcp and the bytes parse to the same message.
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
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY or not P._importable("zmq"),
                                reason=P.SKIP_PY + " + pyzmq")

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_zmq"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture()
def ctx():
    import zmq
    c = zmq.Context()
    yield c
    c.destroy(linger=0)


def _z(name):
    return importlib.import_module("harpia_generated.zmq.{}_{}_zmq".format(name, HASH))


def _free_tcp():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "tcp://127.0.0.1:{}".format(port)


def _timeout(r, ms=3000):
    import zmq
    r.socket.setsockopt(zmq.RCVTIMEO, ms)
    return r


def test_module_set_roles_and_origin_ids_match_cpp(gen):
    cpp_dir = os.path.join(gen, "generated", "cpp", "zmq")
    cpp = {f[:-len("_zmq.h")] for f in os.listdir(cpp_dir) if f.endswith("_zmq.h")}
    py_dir = os.path.join(P.py_root(gen), "harpia_generated", "zmq")
    py = {f[:-len("_zmq.py")] for f in os.listdir(py_dir) if f.endswith("_zmq.py")}
    assert py == cpp and cpp
    for stem in cpp:
        header = open(os.path.join(cpp_dir, stem + "_zmq.h")).read()
        mod = _z(stem[:-len("_" + HASH)])
        cpp_id = re.search(r'static const std::string id = "(\d+)";', header).group(1)
        assert mod.ORIGIN_ID == cpp_id
        for role in ("sender", "receiver", "publisher", "subscriber"):
            assert hasattr(mod, "new_" + role) == ("_" + role + "(" in header), (stem, role)


@pytest.mark.parametrize("transport", ["inproc", "tcp"])
def test_push_pull_round_trip_and_runtime_origin(transport, gen, ctx):
    z = _z("courier")
    ep = "inproc://courier-pp" if transport == "inproc" else _free_tcp()
    rx = _timeout(z.new_receiver(ctx, ep))
    a, b = z.new_sender(ctx, ep), z.new_sender(ctx, ep)
    assert a.origin != b.origin and re.fullmatch(r"\d+-\d+-[0-9a-f]+", a.origin)
    msg = z.courier()
    setattr(msg, PK, 9)
    assert a.send(msg)
    got = rx.recv()
    assert got is not None and getattr(got, PK) == 9
    field = next(f.name for f in got.DESCRIPTOR.fields if f.name.startswith("ORIGINATOR"))
    assert getattr(got, field) == a.origin and getattr(msg, field) == ""  # caller's copy untouched
    for s in (a, b, rx):
        s.close()


@pytest.mark.parametrize("transport", ["inproc", "tcp"])
def test_pub_sub_round_trip_one_to_many_origin(transport, gen, ctx):
    z = _z("users")
    ep = "inproc://users-ps" if transport == "inproc" else _free_tcp()
    pub = z.new_publisher(ctx, ep)
    sub = _timeout(z.new_subscriber(ctx, ep), 200)
    assert pub.origin == z.ORIGIN_ID
    msg = z.users()
    msg.name = "neo"
    got = None
    for _ in range(50):  # slow joiner: publish until the subscription is live
        pub.publish(msg)
        got = sub.receive()
        if got is not None:
            break
    assert got is not None and got.name == "neo"
    field = next(f.name for f in got.DESCRIPTOR.fields if f.name.startswith("ORIGINATOR"))
    assert getattr(got, field) == z.ORIGIN_ID
    pub.close()
    sub.close()


def test_garbage_frame_is_none(gen, ctx):
    import zmq
    z = _z("courier")
    rx = _timeout(z.new_receiver(ctx, "inproc://garbage"))
    raw = ctx.socket(zmq.PUSH)
    raw.connect("inproc://garbage")
    raw.send(b"\xff\xff\xff\xff")
    assert rx.recv() is None
    raw.close(linger=0)
    rx.close()


def test_fan_out_every_subscriber_gets_every_message(gen, ctx):
    z = _z("users")
    pub = z.new_publisher(ctx, "inproc://fanout")
    subs = [_timeout(z.new_subscriber(ctx, "inproc://fanout"), 200) for _ in range(3)]
    probe = z.users()
    probe.name = "probe"
    ready = set()
    deadline = time.monotonic() + 10
    while len(ready) < len(subs) and time.monotonic() < deadline:
        pub.publish(probe)
        for i, s in enumerate(subs):
            while (m := s.receive()) is not None:
                ready.add(i)
    assert len(ready) == 3
    for s in subs:  # drain the probes
        while s.receive() is not None:
            pass
    for i in range(20):
        m = z.users()
        setattr(m, PK, i + 1)
        pub.publish(m)
    for s in subs:
        got = [getattr(s.receive(), PK) for _ in range(20)]
        assert got == list(range(1, 21))
    for s in subs + [pub]:
        s.close()


def test_push_pull_load_balance_exactly_once(gen, ctx):
    import zmq
    z = _z("courier")
    pullers = [_timeout(z.new_receiver(ctx, "inproc://lb{}".format(i)), 200) for i in range(3)]
    sender = z.new_sender(ctx, "inproc://lb0")
    for i in (1, 2):
        sender.socket.connect("inproc://lb{}".format(i))
    time.sleep(0.1)
    for i in range(30):
        m = z.courier()
        setattr(m, PK, i + 1)
        assert sender.send(m)
    seen, per = [], []
    for p in pullers:
        got = []
        while (m := p.recv()) is not None:
            got.append(getattr(m, PK))
        per.append(len(got))
        seen += got
    assert sorted(seen) == list(range(1, 31))  # each exactly once
    assert all(n > 0 for n in per), per  # actually balanced across peers
    for s in pullers + [sender]:
        s.close()
    assert zmq  # imported for the socket options above


_CPP = r'''
#include <chrono>
#include <thread>
#include "zmq/courier_%(h)s_zmq.h"
int main(int, char** argv) {
    ::zmq::context_t ctx;
    harpia::zmq_transport::courier_sender s(ctx, argv[1], "cpp-origin");
    s.socket().set(::zmq::sockopt::linger, 2000);
    ::courier c; c.set_id_%(h)s(77);
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    return s.send(c) ? 0 : 3;
}
'''


@pytest.mark.skipif(shutil.which("g++") is None or not os.path.exists("/usr/include/zmq.hpp"),
                    reason="needs g++ + cppzmq")
def test_cpp_sender_python_receiver(gen, ctx, tmp_path):
    cpp_root = os.path.join(gen, "generated", "cpp")
    (tmp_path / "s.cpp").write_text(_CPP % {"h": HASH})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf", "libzmq"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "s"
    pb = os.path.join(cpp_root, "protofiles", "courier_{}.pb.cc".format(HASH))
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(tmp_path / "s.cpp"), pb,
                        "-o", str(exe), *flags, "-lpthread"],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    z = _z("courier")
    ep = _free_tcp()
    rx = _timeout(z.new_receiver(ctx, ep), 10000)
    run = subprocess.run([str(exe), ep], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    got = rx.recv()
    assert got is not None and getattr(got, PK) == 77
    field = next(f.name for f in got.DESCRIPTOR.fields if f.name.startswith("ORIGINATOR"))
    assert getattr(got, field) == "cpp-origin"
    rx.close()
