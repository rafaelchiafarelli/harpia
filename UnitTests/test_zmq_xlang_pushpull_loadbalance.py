"""transport-multipeer-coverage / zmq-multipeer task 5 -- cross-language
PUSH/PULL load-balance (C++ + Java).

Same scenario as task 2 (`test_zmq_pushpull_loadbalance.py`), but the 3
pullers are split across languages -- 2 real C++ processes + 1 real Java
process -- over a real `tcp://` socket. `courier` (push-only,
`HarpiaTest/Include/file3.harpia`) is the same fixture task 2 used.

Orchestration mirrors task 4's event-driven readiness signaling, adapted for
PUSH/PULL: each puller process binds an ephemeral port, prints it, sleeps a
short settle, prints "READY", then drains until it times out (no more work
coming) and prints its received sequence numbers. Only once all 3 pullers
are bound and ready does the parent start the C++ pusher, given all 3
endpoints on argv (its ctor connects to the first, two more `connect()`
calls on the raw socket fan it out to the other two, same shape as task 2).

protoc+g+++pkg-config **and** gradle+JDK gated (same combined gating as
task 4):

    Docker/run.sh pytest UnitTests/test_zmq_xlang_pushpull_loadbalance.py
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


def _have_libzmq():
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


_HAS_CPP_TOOLCHAIN = (
    shutil.which("protoc") is not None
    and shutil.which("g++") is not None
    and shutil.which("pkg-config") is not None
    and _have_libzmq()
    and os.path.exists("/usr/include/zmq.hpp")
)
_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None

pytestmark = pytest.mark.skipif(
    not _HAS_CPP_TOOLCHAIN or not _HAS_JAVA_TOOLCHAIN,
    reason="needs protoc+g+++pkg-config+libzmq+cppzmq AND gradle+JDK (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath  # noqa: E402


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def _read_marker_value(proc, prefix, max_lines=50):
    """Like _java_gradle_helpers.wait_for_listening, but returns the text
    after `prefix` on the first matching line instead of discarding it --
    needed here since the marker itself (ENDPOINT:<addr>) carries the value
    the rest of the test needs. Tolerates noise lines before it (e.g.
    JeroMQ/SLF4J's static-init warning on first touching org.zeromq)."""
    lines = []
    for _ in range(max_lines):
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    proc.kill()
    proc.communicate(timeout=10)
    raise AssertionError(
        "{} never printed a line starting with {!r} within {} lines:\n{}".format(
            proc.args, prefix, max_lines, "".join(lines)))


@pytest.fixture(scope="module")
def cpp_built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_xlang_pp_cpp")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(build, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")
    pb_cc = os.path.join(proto_dir, "courier_{}.pb.cc".format(HASH))

    def _build(name, source):
        src_path = os.path.join(str(out), name + ".cc")
        with open(src_path, "w") as f:
            f.write(source)
        binary = os.path.join(str(out), name)
        cmd = ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
              src_path, pb_cc, "-o", binary, *_pkgconfig("--libs")]
        c = subprocess.run(cmd, capture_output=True, text=True)
        assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
        return binary

    push_src = '''
#include "zmq/courier_{h}_zmq.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>

int main(int argc, char** argv) {{
    if (argc < 5) return 100;
    std::string e1 = argv[1], e2 = argv[2], e3 = argv[3];
    int n = std::atoi(argv[4]);
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::courier_sender snd(ctx, e1);
    snd.socket().set(::zmq::sockopt::linger, 0);
    snd.socket().connect(e2);
    snd.socket().connect(e3);
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    for (int i = 1; i <= n; ++i) {{
        ::courier m;
        m.set_payload("seq-" + std::to_string(i));
        if (!snd.send(m)) return 1;
    }}
    return 0;
}}
'''.format(h=HASH)

    pull_src = '''
#include "zmq/courier_{h}_zmq.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <string>
#include <thread>

int main(int argc, char** argv) {{
    if (argc < 2) return 100;
    int max_n = std::atoi(argv[1]);
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::courier_receiver rcv(ctx, "tcp://127.0.0.1:*");
    rcv.socket().set(::zmq::sockopt::linger, 0);
    std::string endpoint = rcv.socket().get(::zmq::sockopt::last_endpoint);
    std::printf("ENDPOINT:%s\\n", endpoint.c_str());
    std::fflush(stdout);
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    std::printf("READY\\n");
    std::fflush(stdout);
    rcv.socket().set(::zmq::sockopt::rcvtimeo, 2000);
    std::ostringstream result;
    bool first = true;
    for (int i = 0; i < max_n; ++i) {{
        ::courier in;
        if (!rcv.recv(&in)) break;   // timed out -- no more work coming
        int seq = std::atoi(in.payload().c_str() + 4);   // "seq-<N>"
        if (!first) result << ",";
        result << seq;
        first = false;
    }}
    std::printf("RESULT:%s\\n", result.str().c_str());
    return 0;
}}
'''.format(h=HASH)

    return {
        "push": _build("xlang_push", push_src),
        "pull": _build("xlang_pull", pull_src),
    }


@pytest.fixture(scope="module")
def java_classpath(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_xlang_pp_java")
    java_out = generate(out, lang="java")
    java_root = os.path.join(java_out, "java")
    return build_and_classpath(java_root, {
        "smoke/ZmqXlangPull.java":
            "package smoke;\n"
            "import com.harpia.generated.courier;\n"
            "import com.harpia.generated.zmq.courier_zmq;\n"
            "import com.harpia.runtime.zmq.HarpiaZmq;\n"
            "import org.zeromq.ZContext;\n"
            "public class ZmqXlangPull {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        int maxN = Integer.parseInt(args[0]);\n"
            "        try (ZContext ctx = new ZContext()) {\n"
            "            HarpiaZmq.Receiver rcv = courier_zmq.newReceiver(ctx, \"tcp://127.0.0.1:*\");\n"
            "            String endpoint = rcv.socket().getLastEndpoint();\n"
            "            System.out.println(\"ENDPOINT:\" + endpoint);\n"
            "            System.out.flush();\n"
            "            Thread.sleep(300);\n"
            "            System.out.println(\"READY\");\n"
            "            System.out.flush();\n"
            "            rcv.socket().setReceiveTimeOut(2000);\n"
            "            StringBuilder result = new StringBuilder();\n"
            "            boolean first = true;\n"
            "            for (int i = 0; i < maxN; i++) {\n"
            "                courier.Builder b = courier.newBuilder();\n"
            "                if (!rcv.receive(b)) break;\n"
            "                int seq = Integer.parseInt(b.getPayload().substring(4));\n"
            "                if (!first) result.append(\",\");\n"
            "                result.append(seq);\n"
            "                first = false;\n"
            "            }\n"
            "            System.out.println(\"RESULT:\" + result.toString());\n"
            "        }\n"
            "    }\n"
            "}\n",
    })


def test_two_cpp_and_one_java_puller_split_the_work(cpp_built, java_classpath):
    pullers = [
        subprocess.Popen([cpp_built["pull"], str(_N)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
        subprocess.Popen([cpp_built["pull"], str(_N)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
        subprocess.Popen(["java", "-cp", java_classpath, "smoke.ZmqXlangPull", str(_N)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
    ]
    try:
        endpoints = [_read_marker_value(p, "ENDPOINT:") for p in pullers]
        for p in pullers:
            _read_marker_value(p, "READY")

        pusher = subprocess.Popen(
            [cpp_built["push"], *endpoints, str(_N)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            push_out, _ = pusher.communicate(timeout=20)
            assert pusher.returncode == 0, "pusher failed:\n" + push_out
        finally:
            if pusher.poll() is None:
                pusher.kill()
                pusher.communicate()

        seen = set()
        per_puller_counts = []
        for i, p in enumerate(pullers):
            out, _ = p.communicate(timeout=20)
            assert p.returncode == 0, "puller {} failed:\n{}".format(i, out)
            result_line = next(
                (l for l in out.splitlines() if l.startswith("RESULT:")), None)
            assert result_line is not None, \
                "puller {} never reported RESULT:\n{}".format(i, out)
            raw = result_line[len("RESULT:"):].strip()
            seqs = [int(x) for x in raw.split(",")] if raw else []
            per_puller_counts.append(len(seqs))
            for s in seqs:
                assert s not in seen, "sequence {} delivered more than once".format(s)
                seen.add(s)

        assert seen == set(range(1, _N + 1)), \
            "union mismatch: missing {}, unexpected {}".format(
                set(range(1, _N + 1)) - seen, seen - set(range(1, _N + 1)))
        for i, count in enumerate(per_puller_counts):
            assert count > 0, "puller {} (lang {}) got nothing".format(
                i, "java" if i == 2 else "cpp")
            assert count < _N, "puller {} got everything -- work didn't distribute".format(i)
    finally:
        for p in pullers:
            if p.poll() is None:
                p.kill()
                p.communicate()
