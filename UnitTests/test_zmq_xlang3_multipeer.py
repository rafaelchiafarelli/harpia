"""python-target / tri-language-interop task 1: ZMQ fan-out + load-balance
with C++, Java and Python peers, plus CURVE + ZAP across languages.

Extends ``test_zmq_xlang_pubsub_fanout.py`` / ``test_zmq_xlang_pushpull_
loadbalance.py`` (C++ + Java) with Python processes, same orchestration
(READY / GO over stdio, the existing 300 ms slow-joiner settle only):

- PUB/SUB fan-out (``pump_tick``): the publisher rotates C++ / Python; one C++,
  one Java and one Python subscriber all receive 1..N in order and decode the
  same stamped ``ORIGINATOR_<hash>`` (= ``ZmqAdapter._origin_id``);
- PUSH/PULL load-balance (``courier``): a C++ pusher (seq 1..N) **and** a
  Python pusher (N+1..2N) at once, into a C++, a Java and a Python puller:
  every sequence delivered exactly once in total, every puller used;
- CURVE + ZAP (hardened profile): the bind side enforces the allowlist --
  C++ and Python ZAP servers, each with a listed and an unlisted client of
  every other language (Java's CURVE has no ZAP server; a Java client
  against both is in scope).

The C++ and Python sides come from one python-target generation (it emits
C++ too); Java from a java-target generation of the same schema (same hash,
same origin ids). Gated on protoc + g++ + libzmq + cppzmq, gradle + JDK and
the Python toolchain.
"""
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
from UnitTests._java_gradle_helpers import (  # noqa: E402
    build_and_classpath, generate, wait_for_listening)
from UnitTests.test_zmq_xlang_pubsub_fanout import _ORIGINATOR_GETTER  # noqa: E402
from ZmqAdapter.ZmqAdapter import _origin_id  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
_N = 12


def _have_libzmq():
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


def _have_pyzmq():
    try:
        import zmq  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not (P.HAVE_PY and _have_pyzmq() and shutil.which("g++") and _have_libzmq()
         and os.path.exists("/usr/include/zmq.hpp")
         and shutil.which("gradle") and shutil.which("java")),
    reason="needs protoc+g+++libzmq+cppzmq, gradle+JDK and the Python toolchain (image)")


def _flags():
    return subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf", "libzmq"],
                          capture_output=True, text=True, check=True).stdout.split()


_CPP = r'''
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include "zmq/@M@_@H@_zmq.h"
using namespace harpia::zmq_transport;
static void settle() { std::this_thread::sleep_for(std::chrono::milliseconds(300)); }
int main(int argc, char** argv) {
    const std::string mode = argv[1];
    ::zmq::context_t ctx{1};
#ifdef HARPIA_TICK
    if (mode == "pub") {                       // pub <n>
        int n = std::atoi(argv[2]);
        pump_tick_publisher pub(ctx, "tcp://127.0.0.1:*");
        pub.socket().set(::zmq::sockopt::linger, 0);
        std::printf("ENDPOINT:%s\n", pub.socket().get(::zmq::sockopt::last_endpoint).c_str());
        std::fflush(stdout);
        std::string line;
        if (!std::getline(std::cin, line)) return 101;
        for (int i = 1; i <= n; ++i) {
            ::pump_tick m; m.set_sequence(i); m.set_rate_mhz(1000 + i);
            if (!pub.publish(m)) return 1;
        }
        return 0;
    }
    if (mode == "sub") {                       // sub <endpoint> <n>
        int n = std::atoi(argv[3]);
        pump_tick_subscriber sub(ctx, argv[2]);
        sub.socket().set(::zmq::sockopt::linger, 0);
        settle();
        std::printf("READY\n"); std::fflush(stdout);
        sub.socket().set(::zmq::sockopt::rcvtimeo, 8000);
        for (int i = 1; i <= n; ++i) {
            ::pump_tick in;
            if (!sub.receive(&in)) { std::printf("ERROR timeout %d\n", i); return 2; }
            if (i == 1) std::printf("ORIGIN:%s\n", in.originator_@H@().c_str());
            if (in.sequence() != i || in.rate_mhz() != 1000 + i) { std::printf("ERROR seq\n"); return 3; }
        }
        std::printf("OK\n");
        return 0;
    }
#else
    if (mode == "push") {                      // push <first> <n> <ep>...
        int first = std::atoi(argv[2]), n = std::atoi(argv[3]);
        courier_sender snd(ctx, argv[4]);
        snd.socket().set(::zmq::sockopt::linger, 2000);
        for (int k = 5; k < argc; ++k) snd.socket().connect(argv[k]);
        std::string line;
        if (!std::getline(std::cin, line)) return 101;   // GO once all connected
        for (int i = first; i < first + n; ++i) {
            ::courier m; m.set_payload("seq-" + std::to_string(i));
            if (!snd.send(m)) return 1;
        }
        return 0;
    }
    if (mode == "pull") {                      // pull <max>
        int max_n = std::atoi(argv[2]);
        courier_receiver rcv(ctx, "tcp://127.0.0.1:*");
        rcv.socket().set(::zmq::sockopt::linger, 0);
        std::printf("ENDPOINT:%s\n", rcv.socket().get(::zmq::sockopt::last_endpoint).c_str());
        settle();
        std::printf("READY\n"); std::fflush(stdout);
        rcv.socket().set(::zmq::sockopt::rcvtimeo, 2500);
        std::ostringstream out; bool first = true;
        for (int i = 0; i < max_n; ++i) {
            ::courier in;
            if (!rcv.recv(&in)) break;
            if (!first) out << ",";
            out << std::atoi(in.payload().c_str() + 4); first = false;
        }
        std::printf("RESULT:%s\n", out.str().c_str());
        return 0;
    }
    if (mode == "curve-server") {              // curve-server <ep> <server_sec>
        courier_receiver r(ctx, argv[2], CurveServerKeys{argv[3]});
        r.socket().set(::zmq::sockopt::rcvtimeo, 4000);
        std::printf("READY\n"); std::fflush(stdout);
        ::courier c;
        if (!r.recv(&c)) return 4;
        return c.payload() == "curve" ? 0 : 5;
    }
    if (mode == "curve-client") {              // curve-client <ep> <spub> <pub> <sec>
        courier_sender s(ctx, argv[2], "cpp", CurveClientKeys{argv[3], argv[4], argv[5]});
        s.socket().set(::zmq::sockopt::linger, 3000);
        ::courier c; c.set_payload("curve");
        settle();
        return s.send(c) ? 0 : 1;
    }
#endif
    return 100;
}
'''

_PY = r'''
import importlib, os, sys, time
root, h, mode, *args = sys.argv[1:]
sys.path.insert(0, root)
import zmq
rt = importlib.import_module("harpia_runtime.zmq")
tick = importlib.import_module("harpia_generated.zmq.pump_tick_%s_zmq" % h)
cour = importlib.import_module("harpia_generated.zmq.courier_%s_zmq" % h)
ctx = zmq.Context()
if mode == "keygen":
    print("KEYS", *rt.generate_curve_keypair())
elif mode == "pub":
    n = int(args[0])
    pub = tick.new_publisher(ctx, "tcp://127.0.0.1:*")
    print("ENDPOINT:" + pub.socket.getsockopt(zmq.LAST_ENDPOINT).decode(), flush=True)
    sys.stdin.readline()
    for i in range(1, n + 1):
        m = tick.pump_tick(sequence=i, rate_mhz=1000 + i)
        assert pub.send(m)
    time.sleep(0.5)
    pub.close()
elif mode == "sub":
    ep, n = args[0], int(args[1])
    sub = tick.new_subscriber(ctx, ep)
    time.sleep(0.3)
    print("READY", flush=True)
    sub.socket.setsockopt(zmq.RCVTIMEO, 8000)
    for i in range(1, n + 1):
        m = sub.recv()
        if m is None:
            print("ERROR timeout", i); sys.exit(2)
        if i == 1:
            print("ORIGIN:" + getattr(m, "ORIGINATOR_" + h))
        if m.sequence != i or m.rate_mhz != 1000 + i:
            print("ERROR seq"); sys.exit(3)
    print("OK")
elif mode == "push":
    first, n, eps = int(args[0]), int(args[1]), args[2:]
    snd = cour.new_sender(ctx, eps[0])
    for ep in eps[1:]:
        snd.socket.connect(ep)
    sys.stdin.readline()
    for i in range(first, first + n):
        assert snd.send(cour.courier(payload="seq-%d" % i))
    snd.socket.setsockopt(zmq.LINGER, 2000)
    snd.socket.close(linger=2000)
elif mode == "pull":
    max_n = int(args[0])
    rcv = cour.new_receiver(ctx, "tcp://127.0.0.1:*")
    print("ENDPOINT:" + rcv.socket.getsockopt(zmq.LAST_ENDPOINT).decode(), flush=True)
    time.sleep(0.3)
    print("READY", flush=True)
    rcv.socket.setsockopt(zmq.RCVTIMEO, 2500)
    seqs = []
    for _ in range(max_n):
        m = rcv.recv()
        if m is None:
            break
        seqs.append(m.payload[4:])
    print("RESULT:" + ",".join(seqs))
elif mode == "curve-server":
    ep, sec = args
    r = cour.new_receiver(ctx, ep, curve=rt.CurveServerKeys(sec))
    r.socket.setsockopt(zmq.RCVTIMEO, 4000)
    print("READY", flush=True)
    m = r.recv()
    r.close()
    sys.exit(0 if m is not None and m.payload == "curve" else 4)
elif mode == "curve-client":
    ep, spub, pub, sec = args
    s = cour.new_sender(ctx, ep, curve=rt.CurveClientKeys(spub, pub, sec))
    time.sleep(0.3)
    assert s.send(cour.courier(payload="curve"))
    s.socket.close(linger=3000)
'''

_JAVA = {
    "smoke/Xlang3.java":
        "package smoke;\n"
        "import com.harpia.generated.courier;\n"
        "import com.harpia.generated.pump_tick;\n"
        "import com.harpia.generated.zmq.courier_zmq;\n"
        "import com.harpia.generated.zmq.pump_tick_zmq;\n"
        "import com.harpia.runtime.zmq.HarpiaZmq;\n"
        "import org.zeromq.ZContext;\n"
        "import org.zeromq.ZMQ;\n"
        "public class Xlang3 {\n"
        "    public static void main(String[] a) throws Exception {\n"
        "        try (ZContext ctx = new ZContext()) {\n"
        "            if (a[0].equals(\"sub\")) {\n"
        "                int n = Integer.parseInt(a[2]);\n"
        "                HarpiaZmq.Receiver sub = pump_tick_zmq.newSubscriber(ctx, a[1]);\n"
        "                Thread.sleep(300);\n"
        "                System.out.println(\"READY\"); System.out.flush();\n"
        "                sub.socket().setReceiveTimeOut(8000);\n"
        "                for (int i = 1; i <= n; i++) {\n"
        "                    pump_tick.Builder b = pump_tick.newBuilder();\n"
        "                    if (!sub.receive(b)) { System.out.println(\"ERROR timeout\"); System.exit(2); }\n"
        "                    pump_tick m = b.build();\n"
        "                    if (i == 1) System.out.println(\"ORIGIN:\" + m." + _ORIGINATOR_GETTER + "());\n"
        "                    if (m.getSequence() != i || m.getRateMhz() != 1000 + i) { System.out.println(\"ERROR seq\"); System.exit(3); }\n"
        "                }\n"
        "                System.out.println(\"OK\");\n"
        "            } else if (a[0].equals(\"pull\")) {\n"
        "                int maxN = Integer.parseInt(a[1]);\n"
        "                HarpiaZmq.Receiver rcv = courier_zmq.newReceiver(ctx, \"tcp://127.0.0.1:*\");\n"
        "                System.out.println(\"ENDPOINT:\" + rcv.socket().getLastEndpoint());\n"
        "                Thread.sleep(300);\n"
        "                System.out.println(\"READY\"); System.out.flush();\n"
        "                rcv.socket().setReceiveTimeOut(2500);\n"
        "                StringBuilder r = new StringBuilder();\n"
        "                for (int i = 0; i < maxN; i++) {\n"
        "                    courier.Builder b = courier.newBuilder();\n"
        "                    if (!rcv.receive(b)) break;\n"
        "                    if (r.length() > 0) r.append(\",\");\n"
        "                    r.append(b.getPayload().substring(4));\n"
        "                }\n"
        "                System.out.println(\"RESULT:\" + r);\n"
        "            } else {\n"
        "                HarpiaZmq.Sender s = courier_zmq.newSender(ctx, a[1], HarpiaZmq.CurveKeys.client(\n"
        "                    ZMQ.Curve.z85Decode(a[2]), ZMQ.Curve.z85Decode(a[3]), ZMQ.Curve.z85Decode(a[4])));\n"
        "                s.socket().setLinger(3000);\n"
        "                Thread.sleep(300);\n"
        "                if (!s.send(courier.newBuilder().setPayload(\"curve\").build())) System.exit(1);\n"
        "                s.socket().close();\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n",
}


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return P.generate_python(tmp_path_factory.mktemp("xlang3_zmq"))


class _Cpp(list):
    """The C++ peer: one binary per message -- two generated zmq/*_zmq.h
    headers can't share a translation unit (both define
    ``runtime_origin_id()``; a C++ finding, logged, not changed here)."""

    def __init__(self, tick, courier):
        super().__init__([tick])
        self.courier = [courier]


@pytest.fixture(scope="module")
def cpp(gen, tmp_path_factory):
    d = tmp_path_factory.mktemp("xlang3_cpp")
    root = os.path.join(gen, "generated", "cpp")
    bins = []
    for name, define in (("pump_tick", ["-DHARPIA_TICK"]), ("courier", [])):
        src = d / ("%s.cpp" % name)
        src.write_text(_CPP.replace("@H@", HASH).replace("@M@", name))
        c = subprocess.run(["g++", "-std=c++17", *define, "-I", root, str(src),
                            os.path.join(root, "protofiles", "%s_%s.pb.cc" % (name, HASH)),
                            "-o", str(d / name), *_flags(), "-lpthread"],
                           capture_output=True, text=True, timeout=600)
        assert c.returncode == 0, c.stderr[-3000:]
        bins.append(str(d / name))
    return _Cpp(*bins)


@pytest.fixture(scope="module")
def java(tmp_path_factory):
    out = tmp_path_factory.mktemp("xlang3_java")
    cp = build_and_classpath(os.path.join(generate(out, lang="java"), "java"), _JAVA)
    return ["java", "-cp", cp, "smoke.Xlang3"]


@pytest.fixture(scope="module")
def py(gen):
    return [sys.executable, "-c", _PY, P.py_root(gen), HASH]


def _start(cmd, *args, **kw):
    return subprocess.Popen([*cmd, *map(str, args)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)


def _value(proc, marker):
    for line in proc.stdout:
        if line.startswith(marker):
            return line[len(marker):].strip()
    pytest.fail("process never printed " + marker)


def _finish(procs, timeout=40):
    outs = []
    for p in procs:
        try:
            out, _ = p.communicate(timeout=timeout)
        finally:
            if p.poll() is None:
                p.kill()
        outs.append((p.returncode, out))
    return outs


@pytest.mark.parametrize("publisher", ["cpp", "python"])
def test_pubsub_fanout_three_languages(publisher, cpp, java, py):
    pub = _start(cpp if publisher == "cpp" else py, "pub", _N)
    endpoint = _value(pub, "ENDPOINT:")
    subs = [_start(cmd, "sub", endpoint, _N) for cmd in (cpp, java, py)]
    try:
        for s in subs:
            wait_for_listening(s, marker="READY")
        pub.stdin.write("GO\n")
        pub.stdin.flush()
        (rc, out), *results = _finish([pub, *subs])
        assert rc == 0, out
    finally:
        for p in (pub, *subs):
            if p.poll() is None:
                p.kill()
    origins = []
    for lang, (rc, out) in zip(("cpp", "java", "python"), results):
        assert rc == 0 and "OK" in out, (lang, out)
        origins.append(next(l for l in out.splitlines() if l.startswith("ORIGIN:"))[7:])
    assert origins == [_origin_id(HASH, "pump_tick")] * 3


def test_pushpull_mixed_pushers_and_pullers(cpp, java, py):
    pullers = [_start(cmd, "pull", 4 * _N) for cmd in (cpp.courier, java, py)]
    try:
        endpoints = [_value(p, "ENDPOINT:") for p in pullers]
        for p in pullers:
            _value(p, "READY")
        pushers = [_start(cpp.courier, "push", 1, _N, *endpoints),
                   _start(py, "push", _N + 1, _N, *endpoints)]
        import time
        time.sleep(0.3)  # the slow-joiner settle: every pusher connected to all
        for p in pushers:
            p.stdin.write("GO\n")
            p.stdin.flush()
        for rc, out in _finish(pushers):
            assert rc == 0, out
        results = _finish(pullers)
    finally:
        for p in pullers:
            if p.poll() is None:
                p.kill()
    seen = []
    for lang, (rc, out) in zip(("cpp", "java", "python"), results):
        assert rc == 0, (lang, out)
        raw = next(l for l in out.splitlines() if l.startswith("RESULT:"))[7:].strip()
        got = [int(x) for x in raw.split(",")] if raw else []
        assert got, "%s puller got nothing" % lang
        seen += got
    assert sorted(seen) == list(range(1, 2 * _N + 1))  # each exactly once


def _free_ep():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "tcp://127.0.0.1:%d" % port


@pytest.fixture(scope="module")
def curve_keys(py):
    def keygen():
        out = subprocess.run([*py, "keygen"], capture_output=True, text=True, check=True)
        return tuple(out.stdout.split()[1:3])
    return {"server": keygen(), "listed": keygen(), "unlisted": keygen()}


@pytest.mark.parametrize("server,client", [("python", "cpp"), ("python", "java"),
                                           ("cpp", "python"), ("cpp", "java")])
@pytest.mark.parametrize("listed", [True, False])
def test_curve_zap_across_languages(server, client, listed, cpp, java, py, curve_keys,
                                    tmp_path):
    spub, ssec = curve_keys["server"]
    gpub, gsec = curve_keys["listed"]
    allow = tmp_path / "allow.txt"
    allow.write_text("%s edge-01\n" % gpub)
    env = dict(os.environ, HARPIA_ZMQ_ALLOWLIST=str(allow))
    ep = _free_ep()
    srv = _start({"python": py, "cpp": cpp.courier}[server], "curve-server", ep, ssec,
                 env=env)
    try:
        assert srv.stdout.readline().strip() == "READY"
        pub, sec = curve_keys["listed" if listed else "unlisted"]
        cli = _start({"python": py, "cpp": cpp.courier, "java": java}[client],
                     "curve-client", ep, spub, pub, sec)
        (crc, cout), = _finish([cli])
        assert crc == 0, cout
        (src, sout), = _finish([srv])
    finally:
        for p in (srv,):
            if p.poll() is None:
                p.kill()
    assert src == (0 if listed else 4), sout
