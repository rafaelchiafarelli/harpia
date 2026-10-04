"""transport-multipeer-coverage / zmq-multipeer task 4 -- cross-language
PUB/SUB fan-out (C++ + Java).

Same scenario as task 1 (`test_zmq_pubsub_fanout.py`), but the 3 fan-out
subscribers are split across languages -- 2 real C++ processes + 1 real
Java process -- proving C++ and Java, generated from the *same* `.harpia`
input, actually interoperate as ZMQ peers of each other over a real
`tcp://` socket, not just each against itself (`test_stage13_zmq.py` /
`test_java_zmq.py` are both 1:1, same-language only).

`pump_tick` (`event[not-cached]`, one-to-* / unique publisher -- so its
hidden field is `ORIGINATOR_<hash>`, not bare `ORIGINATOR`) is the same
fixture task 1 used. This also makes real the "watch for" item in
epics/README.md: both runtimes find the ORIGINATOR field by NAME PREFIX
(C++ at codegen time, Java at runtime via reflection on the SENDER side
only -- see `JavaZmqAdapter/CLAUDE.md`), so this asserts every subscriber,
in both languages, decodes the exact same stamped value a C++ publisher
wrote, matching the value `ZmqAdapter._origin_id()` itself would compute.

Orchestration: the C++ publisher process binds an ephemeral `tcp://` port,
prints it, then blocks on stdin for a "GO" line. Each of the 3 subscriber
processes (2 C++, 1 Java) connects, sleeps the same slow-joiner settle used
elsewhere in this suite, prints "READY", then blocks receiving. The parent
only sends "GO" once all 3 have reported ready -- event-driven, not a blind
sleep guess across a JVM-start + 2-language process fan-out.

protoc+g+++pkg-config **and** gradle+JDK gated (same combined gating as
`UnitTests/test_java_zmq.py`'s own toolchain needs, plus the C++ side):

    Docker/run.sh pytest UnitTests/test_zmq_xlang_pubsub_fanout.py
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
_N = 10


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

from UnitTests._java_gradle_helpers import (  # noqa: E402
    generate, build_and_classpath, wait_for_listening)
from ZmqAdapter.ZmqAdapter import _origin_id  # noqa: E402


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def _java_camel_case(name, cap_first=True):
    """protoc's own UnderscoresToCamelCase (java/helpers.cc): a digit always
    forces the next letter to capitalize, same as an underscore -- so
    "ORIGINATOR_3ac5d8b36..." becomes "ORIGINATOR3Ac5D8B36..." (every letter
    right after a digit run capitalizes), not the naive "strip underscore,
    keep case" guess. Derived here instead of hardcoded so a future HASH
    bump doesn't silently leave a stale getter name behind."""
    result = []
    cap_next = cap_first
    for c in name:
        if "a" <= c <= "z":
            result.append(c.upper() if cap_next else c)
            cap_next = False
        elif "A" <= c <= "Z":
            result.append(c if (cap_next or result) else c.lower())
            cap_next = False
        elif "0" <= c <= "9":
            result.append(c)
            cap_next = True
        else:
            cap_next = True
    return "".join(result)


_ORIGINATOR_FIELD = "ORIGINATOR_{}".format(HASH)
_ORIGINATOR_GETTER = "get" + _java_camel_case(_ORIGINATOR_FIELD)


@pytest.fixture(scope="module")
def cpp_built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_xlang_cpp")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(build, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")
    pb_cc = os.path.join(proto_dir, "pump_tick_{}.pb.cc".format(HASH))

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

    pub_src = '''
#include "zmq/pump_tick_{h}_zmq.h"
#include <cstdio>
#include <iostream>
#include <string>

int main(int argc, char** argv) {{
    if (argc < 2) return 100;
    int n = std::atoi(argv[1]);
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::pump_tick_publisher pub(ctx, "tcp://127.0.0.1:*");
    pub.socket().set(::zmq::sockopt::linger, 0);
    std::string endpoint = pub.socket().get(::zmq::sockopt::last_endpoint);
    std::printf("ENDPOINT:%s\\n", endpoint.c_str());
    std::fflush(stdout);
    std::string line;
    if (!std::getline(std::cin, line)) return 101;   // block for "GO"
    for (int i = 1; i <= n; ++i) {{
        ::pump_tick m;
        m.set_sequence(i);
        m.set_rate_mhz(1000 + i);
        if (!pub.publish(m)) return 1;
    }}
    return 0;
}}
'''.format(h=HASH)

    sub_src = '''
#include "zmq/pump_tick_{h}_zmq.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>

int main(int argc, char** argv) {{
    if (argc < 3) return 100;
    std::string endpoint = argv[1];
    int n = std::atoi(argv[2]);
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::pump_tick_subscriber sub(ctx, endpoint);
    sub.socket().set(::zmq::sockopt::linger, 0);
    std::this_thread::sleep_for(std::chrono::milliseconds(300));  // slow-joiner settle
    std::printf("READY\\n");
    std::fflush(stdout);
    sub.socket().set(::zmq::sockopt::rcvtimeo, 8000);
    for (int i = 1; i <= n; ++i) {{
        ::pump_tick in;
        if (!sub.receive(&in)) {{ std::printf("ERROR timeout at %d\\n", i); return 2; }}
        if (i == 1) {{ std::printf("ORIGIN:%s\\n", in.originator_{h}().c_str()); }}
        if (in.sequence() != i) {{ std::printf("ERROR seq %d want %d\\n", in.sequence(), i); return 3; }}
        if (in.rate_mhz() != 1000 + i) {{ std::printf("ERROR rate\\n"); return 4; }}
    }}
    std::printf("OK\\n");
    return 0;
}}
'''.format(h=HASH)

    return {
        "pub": _build("xlang_pub", pub_src),
        "sub": _build("xlang_sub", sub_src),
    }


@pytest.fixture(scope="module")
def java_classpath(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_xlang_java")
    java_out = generate(out, lang="java")
    java_root = os.path.join(java_out, "java")
    return build_and_classpath(java_root, {
        "smoke/ZmqXlangSub.java":
            "package smoke;\n"
            "import com.harpia.generated.pump_tick;\n"
            "import com.harpia.generated.zmq.pump_tick_zmq;\n"
            "import com.harpia.runtime.zmq.HarpiaZmq;\n"
            "import org.zeromq.ZContext;\n"
            "public class ZmqXlangSub {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        String endpoint = args[0];\n"
            "        int n = Integer.parseInt(args[1]);\n"
            "        try (ZContext ctx = new ZContext()) {\n"
            "            HarpiaZmq.Receiver sub = pump_tick_zmq.newSubscriber(ctx, endpoint);\n"
            "            Thread.sleep(300);\n"
            "            System.out.println(\"READY\");\n"
            "            System.out.flush();\n"
            "            sub.socket().setReceiveTimeOut(8000);\n"
            "            for (int i = 1; i <= n; i++) {\n"
            "                pump_tick.Builder b = pump_tick.newBuilder();\n"
            "                if (!sub.receive(b)) {\n"
            "                    System.out.println(\"ERROR timeout at \" + i);\n"
            "                    System.exit(2);\n"
            "                }\n"
            "                pump_tick msg = b.build();\n"
            "                if (i == 1) {\n"
            "                    System.out.println(\"ORIGIN:\" + msg." + _ORIGINATOR_GETTER + "());\n"
            "                }\n"
            "                if (msg.getSequence() != i) { System.out.println(\"ERROR seq\"); System.exit(3); }\n"
            "                if (msg.getRateMhz() != 1000 + i) { System.out.println(\"ERROR rate\"); System.exit(4); }\n"
            "            }\n"
            "            System.out.println(\"OK\");\n"
            "        }\n"
            "    }\n"
            "}\n",
    })


def test_cpp_and_java_subscribers_all_receive_every_message(cpp_built, java_classpath):
    expected_origin = _origin_id(HASH, "pump_tick")

    pub = subprocess.Popen([cpp_built["pub"], str(_N)],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
    try:
        endpoint_line = pub.stdout.readline()
        assert endpoint_line.startswith("ENDPOINT:"), \
            "publisher never printed its endpoint:\n" + endpoint_line
        endpoint = endpoint_line[len("ENDPOINT:"):].strip()

        subs = [
            subprocess.Popen([cpp_built["sub"], endpoint, str(_N)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
            subprocess.Popen([cpp_built["sub"], endpoint, str(_N)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
            subprocess.Popen(["java", "-cp", java_classpath, "smoke.ZmqXlangSub",
                              endpoint, str(_N)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
        ]
        try:
            for s in subs:
                wait_for_listening(s, marker="READY")

            pub.stdin.write("GO\n")
            pub.stdin.flush()

            pub_out, _ = pub.communicate(timeout=20)
            assert pub.returncode == 0, "publisher failed:\n" + pub_out

            origins = []
            for i, s in enumerate(subs):
                out, _ = s.communicate(timeout=20)
                assert s.returncode == 0, \
                    "subscriber {} failed (rc={}):\n{}".format(i, s.returncode, out)
                assert "OK" in out, "subscriber {} never reported OK:\n{}".format(i, out)
                origin_line = next(
                    (l for l in out.splitlines() if l.startswith("ORIGIN:")), None)
                assert origin_line, "subscriber {} never reported ORIGIN:\n{}".format(i, out)
                origins.append(origin_line[len("ORIGIN:"):].strip())

            # all 3 subscribers -- 2 C++, 1 Java -- decoded the exact same
            # stamped ORIGINATOR value, and it matches what ZmqAdapter's own
            # deterministic derivation would compute for this sender.
            assert origins == [expected_origin] * 3, origins
        finally:
            for s in subs:
                if s.poll() is None:
                    s.kill()
                    s.communicate()
    finally:
        if pub.poll() is None:
            pub.kill()
            pub.communicate()
