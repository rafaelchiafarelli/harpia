"""transport-multipeer-coverage / zmq-multipeer task 1 -- PUB/SUB fan-out,
same language (C++).

The generated ZMQ transport is only ever proven 1-publisher-to-1-subscriber
elsewhere (`test_stage13_zmq.py`, `test_critical_delivery_roundtrip.py`).
This drives one `pump_tick_publisher` and real, separate `pump_tick_subscriber`
objects over a real `tcp://` socket (the realistic multi-peer case, not
`inproc://`) and proves:

  - all 3 already-joined subscribers receive every one of N published
    messages, in order, with correct field values (not just a count), and
  - a 4th subscriber that joins only after the first burst has been sent
    receives nothing from that burst (the classic ZMQ "slow joiner" is
    explicit and asserted here, not an implicit assumption), then receives a
    second burst sent after it joined.

`pump_tick` (`event[not-cached] message`, `HarpiaTest/Include/file3.harpia`)
is used because its own `sequence` field is already the monotonic counter
this task wants stamped per message -- no `.harpia` change needed.

Skipped unless protoc + g++ + pkg-config + libzmq + cppzmq are present, so
the host suite stays green; runs fully in the harpia Docker image:

    Docker/run.sh pytest UnitTests/test_zmq_pubsub_fanout.py
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


def _have_libzmq():
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


pytestmark = pytest.mark.skipif(
    shutil.which("protoc") is None
    or shutil.which("g++") is None
    or shutil.which("pkg-config") is None
    or not _have_libzmq()
    or not os.path.exists("/usr/include/zmq.hpp"),
    reason="needs protoc + g++ + libzmq + cppzmq (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_zmq_pubsub_fanout")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "cpp_root": cpp_root,
        "zmq_dir": os.path.join(cpp_root, "zmq"),
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tmp": str(out),
    }


def _build_and_run(built, name, source, pb_names, timeout=60):
    prog = os.path.join(built["tmp"], name + ".cc")
    with open(prog, "w") as f:
        f.write(source)
    pb_ccs = [os.path.join(built["proto_dir"], "{}_{}.pb.cc".format(p, HASH))
              for p in pb_names]
    binary = os.path.join(built["tmp"], name)
    cmd = ["g++", "-std=c++17",
           "-I", built["cpp_root"], *_pkgconfig("--cflags"),
           prog, *pb_ccs, "-o", binary, *_pkgconfig("--libs")]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return subprocess.run([binary], capture_output=True, text=True,
                          timeout=timeout)


# Same settle window as test_critical_delivery_roundtrip.py's _SETTLE_MS --
# 300ms on loopback is ~1000x the real subscription-propagation time.
_SETTLE_MS = 300


def test_three_subscribers_all_receive_every_message_in_order(built):
    adapter = "pump_tick_{}_zmq.h".format(HASH)
    assert os.path.exists(os.path.join(built["zmq_dir"], adapter)), \
        "pump_tick transport missing"

    src = '''
#include "zmq/pump_tick_{h}_zmq.h"
#include <chrono>
#include <thread>

int main() {{
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::pump_tick_publisher pub(ctx, "tcp://127.0.0.1:*");
    pub.socket().set(::zmq::sockopt::linger, 0);
    std::string endpoint = pub.socket().get(::zmq::sockopt::last_endpoint);

    harpia::zmq_transport::pump_tick_subscriber sub1(ctx, endpoint);
    harpia::zmq_transport::pump_tick_subscriber sub2(ctx, endpoint);
    harpia::zmq_transport::pump_tick_subscriber sub3(ctx, endpoint);
    for (auto* s : {{&sub1, &sub2, &sub3}}) {{
        s->socket().set(::zmq::sockopt::linger, 0);
        s->socket().set(::zmq::sockopt::rcvtimeo, 3000);
    }}
    std::this_thread::sleep_for(std::chrono::milliseconds({settle}));

    const int kN = 10;
    for (int i = 1; i <= kN; ++i) {{
        ::pump_tick m;
        m.set_sequence(i);
        m.set_rate_mhz(1000 + i);
        if (!pub.publish(m)) return 1;
    }}

    for (auto* s : {{&sub1, &sub2, &sub3}}) {{
        for (int expect = 1; expect <= kN; ++expect) {{
            ::pump_tick in;
            if (!s->receive(&in)) return 2;
            if (in.sequence() != expect) return 3;
            if (in.rate_mhz() != 1000 + expect) return 4;
        }}
    }}
    return 0;
}}
'''.format(h=HASH, settle=_SETTLE_MS)
    run = _build_and_run(built, "pubsub_fanout_basic", src, ["pump_tick"])
    assert run.returncode == 0, \
        "fan-out check failed at #{}\n{}".format(run.returncode, run.stderr)


def test_late_joining_subscriber_misses_first_burst_gets_second(built):
    adapter = "pump_tick_{}_zmq.h".format(HASH)
    assert os.path.exists(os.path.join(built["zmq_dir"], adapter)), \
        "pump_tick transport missing"

    src = '''
#include "zmq/pump_tick_{h}_zmq.h"
#include <chrono>
#include <thread>

int main() {{
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::pump_tick_publisher pub(ctx, "tcp://127.0.0.1:*");
    pub.socket().set(::zmq::sockopt::linger, 0);
    std::string endpoint = pub.socket().get(::zmq::sockopt::last_endpoint);

    // --- first burst: no subscriber has joined yet. ---
    const int kFirstBurst = 10;
    for (int i = 1; i <= kFirstBurst; ++i) {{
        ::pump_tick m;
        m.set_sequence(i);
        m.set_rate_mhz(1000 + i);
        if (!pub.publish(m)) return 1;
    }}

    // --- subscriber joins AFTER the first burst was already sent. ---
    harpia::zmq_transport::pump_tick_subscriber late(ctx, endpoint);
    late.socket().set(::zmq::sockopt::linger, 0);
    std::this_thread::sleep_for(std::chrono::milliseconds({settle}));

    // Nothing from the first burst is pending -- prove it with a short
    // timeout rather than assuming: a real message would arrive well within
    // this window, so a timeout here is the "received nothing" assertion.
    late.socket().set(::zmq::sockopt::rcvtimeo, 200);
    ::pump_tick spurious;
    if (late.receive(&spurious)) return 2;  // must NOT have anything queued

    // --- second burst, sent after the late subscriber joined. ---
    late.socket().set(::zmq::sockopt::rcvtimeo, 3000);
    const int kSecondBurst = 5;
    for (int i = 1; i <= kSecondBurst; ++i) {{
        ::pump_tick m;
        m.set_sequence(100 + i);
        m.set_rate_mhz(2000 + i);
        if (!pub.publish(m)) return 3;
    }}
    for (int i = 1; i <= kSecondBurst; ++i) {{
        ::pump_tick in;
        if (!late.receive(&in)) return 4;
        if (in.sequence() != 100 + i) return 5;
        if (in.rate_mhz() != 2000 + i) return 6;
    }}
    return 0;
}}
'''.format(h=HASH, settle=_SETTLE_MS)
    run = _build_and_run(built, "pubsub_fanout_late_joiner", src, ["pump_tick"])
    assert run.returncode == 0, \
        "late-joiner check failed at #{}\n{}".format(run.returncode, run.stderr)
