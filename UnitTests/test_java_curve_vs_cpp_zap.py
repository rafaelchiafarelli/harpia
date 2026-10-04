"""multi-system-reference / java-hardened-client task 3 -- a Java CURVE
subscriber against a C++ CURVE publisher that enforces the ZAP allowlist.

`test_java_zmq_curve.py` proves Java CURVE against Java, and `test_zmq_zap.py`
proves the C++ ZAP allowlist against a C++ client. Nothing proved the pair
the reference system actually runs: `edge` (C++, hardened PUB, CURVE server
+ ZAP) publishing to `handheld` (Java/JeroMQ SUB, CURVE client). No Java
change was needed: JeroMQ's CURVE client is accepted by libzmq's ZAP handler
as-is (no ZAP domain or identity to set), and JeroMQ-generated keys work
unchanged on the libzmq side (Z85 across the process boundary).

Per case: the Java probe generates the client keypair; Python writes
HARPIA_ZMQ_ALLOWLIST; the C++ publisher (generated `users_publisher`, CURVE
server, explicit `harpia::zap::ZapHandler` with a counting AuditSink) binds
and prints its public key + endpoint; the Java subscriber connects and prints
READY; only then does Python send GO and the publisher sends 30 messages over
3 s (covers PUB/SUB slow-joiner and the first-datagram drop documented in
`test_zmq_zap.py`). The publisher then reports its audited denials.

    allowlisted Java key         -> receives, 0 denials (and again with a key
                                    that contains '#', pinned: this pairing is
                                    what found fixes/000005, where the C++
                                    allowlist parser cut lines at '#' -- a Z85
                                    digit -- and denied ~37% of valid keys)
    unknown Java key             -> receives nothing, >= 1 `zap_denied` record
                                    naming that public key, no secret in it
    wrong server public key      -> receives nothing (CURVE handshake fails
                                    before ZAP; never a plaintext fallback)

protoc + g++ + libzmq + cppzmq AND gradle+JDK gated:

    Docker/run.sh pytest UnitTests/test_java_curve_vs_cpp_zap.py
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
_N = 30

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath  # noqa: E402


def _have_libzmq():
    return (shutil.which("pkg-config") is not None
            and subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0)


pytestmark = pytest.mark.skipif(
    shutil.which("protoc") is None
    or shutil.which("g++") is None
    or not _have_libzmq()
    or not os.path.exists("/usr/include/zmq.hpp")
    or shutil.which("gradle") is None
    or shutil.which("java") is None,
    reason="needs protoc + g++ + libzmq + cppzmq AND gradle+JDK (harpia Docker image)",
)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


_PUB_CC = r"""
#include "zmq/users_{h}_zmq.h"
#include <zmq.h>
#include <atomic>
#include <chrono>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>

struct CountingSink : ::harpia::compliance::AuditSink {{
    std::atomic<int> denials{{0}};
    std::mutex m;
    std::string last;
    void record(const std::string& op, const std::string&,
                const std::string& detail) override {{
        if (op != "zap_denied") return;
        ++denials;
        std::lock_guard<std::mutex> lk(m);
        last = detail;
    }}
}};

// argv: expected_denied_pub_z85 client_secret_z85 (for the audit checks).
// HARPIA_ZMQ_ALLOWLIST comes from the environment.
int main(int, char** argv) {{
    const std::string watch_pub = argv[1], client_sec = argv[2];
    char p[41], s[41];
    if (zmq_curve_keypair(p, s) != 0) return 10;
    const std::string spub = p, ssec = s;

    ::zmq::context_t ctx{{1}};
    CountingSink sink;
    harpia::zap::ZapHandler zh(ctx, sink);   // owns inproc://zeromq.zap.01
    if (!zh.active()) return 9;
    harpia::zmq_transport::users_publisher pub(
        ctx, "tcp://127.0.0.1:*", "edge-test",
        harpia::zmq_transport::CurveServerKeys{{ssec}});
    pub.socket().set(::zmq::sockopt::linger, 0);
    std::cout << "SERVERKEY " << spub << "\n"
              << "ENDPOINT " << pub.socket().get(::zmq::sockopt::last_endpoint) << "\n"
              << "LISTENING" << std::endl;

    std::string line;
    if (!std::getline(std::cin, line) || line != "GO") return 11;
    for (int i = 0; i < {n}; ++i) {{
        ::users out; out.set_name("neo"); out.set_address("matrix");
        pub.publish(out);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }}
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    std::lock_guard<std::mutex> lk(sink.m);
    const bool key_seen = sink.last.find(watch_pub) != std::string::npos;
    const bool leak = sink.last.find(client_sec) != std::string::npos
                   || sink.last.find(ssec) != std::string::npos;
    std::cout << "DENIALS " << sink.denials.load()
              << " KEYSEEN " << (key_seen ? 1 : 0)
              << " LEAK " << (leak ? 1 : 0) << std::endl;
    return 0;
}}
"""

_PROBE_JAVA = """\
package smoke;

import com.harpia.generated.users;
import com.harpia.generated.zmq.users_zmq;
import com.harpia.runtime.zmq.HarpiaZmq;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

// keygen [hash]                        -> "KEYS <pub_z85> <sec_z85>"
//                                         (hash: public key contains '#')
// sub <endpoint> <server_pub_z85> <client_pub_z85> <client_sec_z85> <window_ms>
//                                      -> "READY", then "RESULT <count>"
public class CurveProbe {
    public static void main(String[] a) throws Exception {
        if (a[0].equals("keygen")) {
            boolean wantHash = a.length > 1 && a[1].equals("hash");
            byte[][] kp = HarpiaZmq.generateCurveKeyPair();
            while (wantHash && !ZMQ.Curve.z85Encode(kp[0]).contains("#")) {
                kp = HarpiaZmq.generateCurveKeyPair();
            }
            System.out.println("KEYS " + ZMQ.Curve.z85Encode(kp[0]) + " "
                               + ZMQ.Curve.z85Encode(kp[1]));
            return;
        }
        HarpiaZmq.CurveKeys keys = HarpiaZmq.CurveKeys.client(
            ZMQ.Curve.z85Decode(a[2]), ZMQ.Curve.z85Decode(a[3]), ZMQ.Curve.z85Decode(a[4]));
        long window = Long.parseLong(a[5]);
        try (ZContext ctx = new ZContext()) {
            HarpiaZmq.Receiver sub = users_zmq.newSubscriber(ctx, a[1], keys);
            sub.socket().setLinger(0);
            sub.socket().setReceiveTimeOut(250);
            Thread.sleep(500);                       // subscription settle
            System.out.println("READY");
            System.out.flush();
            int count = 0;
            long end = System.currentTimeMillis() + window;
            while (System.currentTimeMillis() < end) {
                users.Builder b = users.newBuilder();
                if (sub.receive(b) && b.getName().equals("neo")) count++;
            }
            System.out.println("RESULT " + count);
        }
    }
}
"""


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("harpia_java_curve_zap"))

    # C++ publisher (repo profile is hardened -> CURVE server applies ZAP)
    r = subprocess.run([sys.executable, RUNNER, tmp], cwd=REPO_ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(tmp, "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(build, "generated", "cpp")
    src = os.path.join(tmp, "zap_pub.cc")
    with open(src, "w") as f:
        f.write(_PUB_CC.format(h=HASH, n=_N))
    pub_bin = os.path.join(tmp, "zap_pub")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"), src,
         os.path.join(cpp_root, "protofiles", "users_{}.pb.cc".format(HASH)),
         "-o", pub_bin, *_pkgconfig("--libs"), "-lpthread"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "publisher failed to build:\n" + c.stderr

    java_out = generate(os.path.join(tmp, "java_gen"), lang="java")
    classpath = build_and_classpath(os.path.join(java_out, "java"),
                                    {"smoke/CurveProbe.java": _PROBE_JAVA})
    return {"tmp": tmp, "pub": pub_bin, "classpath": classpath}


def _java(built, *args, **kw):
    return ["java", "-cp", built["classpath"], "smoke.CurveProbe", *args]


def _keygen(built, with_hash=False):
    args = ("keygen", "hash") if with_hash else ("keygen",)
    r = subprocess.run(_java(built, *args), capture_output=True, text=True, timeout=60)
    line = next((l for l in r.stdout.splitlines() if l.startswith("KEYS ")), None)
    assert line, r.stdout + r.stderr
    _, pub, sec = line.split()
    return pub, sec


def _read_until(proc, marker, max_lines=60):
    """Collect `proc`'s stdout lines up to and including `marker`."""
    lines = []
    for _ in range(max_lines):
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip("\n"))
        if line.strip() == marker:
            return lines
    proc.kill()
    raise AssertionError("never saw {!r}:\n{}".format(marker, "\n".join(lines)))


def _run_case(built, name, allowed_pub, client_pub, client_sec, server_key_override=None):
    allowlist = os.path.join(built["tmp"], "allow_{}.txt".format(name))
    with open(allowlist, "w", encoding="utf-8") as fh:
        fh.write("{} handheld\n".format(allowed_pub))
    pub = subprocess.Popen([built["pub"], client_pub, client_sec],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True,
                           env={**os.environ, "HARPIA_ZMQ_ALLOWLIST": allowlist})
    sub = None
    try:
        head = dict(l.split(" ", 1) for l in _read_until(pub, "LISTENING")
                    if l.startswith(("SERVERKEY ", "ENDPOINT ")))
        server_pub = server_key_override or head["SERVERKEY"]
        sub = subprocess.Popen(
            _java(built, "sub", head["ENDPOINT"], server_pub, client_pub, client_sec,
                  str(_N * 100 + 3000)),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        _read_until(sub, "READY")
        pub.stdin.write("GO\n")
        pub.stdin.flush()
        sub_out, _ = sub.communicate(timeout=60)
        pub_out, _ = pub.communicate(timeout=60)
    finally:
        for p in (sub, pub):
            if p is not None and p.poll() is None:
                p.kill()
                p.wait(timeout=10)
    assert pub.returncode == 0, "publisher rc={}:\n{}".format(pub.returncode, pub_out)
    result = next(l for l in sub_out.splitlines() if l.startswith("RESULT "))
    stats = next(l for l in pub_out.splitlines() if l.startswith("DENIALS ")).split()
    return {"received": int(result.split()[1]), "denials": int(stats[1]),
            "key_seen": stats[3] == "1", "leak": stats[5] == "1"}


def test_allowlisted_java_key_receives(built):
    pub, sec = _keygen(built)
    r = _run_case(built, "allowed", pub, pub, sec)
    assert r["received"] > 0, r
    assert r["denials"] == 0, r


def test_allowlisted_java_key_containing_hash_receives(built):
    # fixes/000005: '#' is a Z85 digit; the C++ allowlist parser used to cut
    # the line there and deny ~37% of legitimately provisioned keys
    pub, sec = _keygen(built, with_hash=True)
    assert "#" in pub
    r = _run_case(built, "allowed_hash", pub, pub, sec)
    assert r["received"] > 0, r
    assert r["denials"] == 0, r


def test_unknown_java_key_is_denied_and_audited(built):
    listed_pub, _ = _keygen(built)
    pub, sec = _keygen(built)
    r = _run_case(built, "unknown", listed_pub, pub, sec)
    assert r["received"] == 0, r
    assert r["denials"] >= 1, r
    assert r["key_seen"], r          # the audit names the rejected public key
    assert not r["leak"], r          # and never a secret key


def test_wrong_server_key_receives_nothing(built):
    pub, sec = _keygen(built)
    bogus_server_pub, _ = _keygen(built)
    r = _run_case(built, "wrongserver", pub, pub, sec,
                  server_key_override=bogus_server_pub)
    assert r["received"] == 0, r
    # the CURVE handshake fails before the ZAP handler is ever consulted
    assert r["denials"] == 0, r
