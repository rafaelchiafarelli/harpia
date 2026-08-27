"""Track D, Session D.4 -- the `critical` send/receive integration test
(Initiatives/medical_devices/epics/thread-6-critical-and-phi-done/histories/critical-delivery/track-d-critical-delivery.md).

One of the two sensitive-data headline deliverables. Drives the *generated*
`alarm_event` transport (`critical event message`, from
HarpiaTest/Include/file3.harpia) over a real ZMQ socket and asserts the
Rule 4a delivery guarantee actually holds end to end:

  1. Held then replayed in order on reconnect -- publish while the
     subscriber is absent (each publish() just enqueues; nothing on the
     wire), then flush() after it joins: every envelope arrives, in seq
     order.
  2. Overflow rotates + audits -- a small bounded queue overrun drops the
     OLDEST, exactly (N - capacity) times, each via an AuditSink
     "queue_rotated" record; the survivors flushed to the wire are the
     newest `capacity`, in order.
  3. A non-`critical` sender on the same kind of path has no queue at all --
     its send() returns bool and fires immediately; there is structurally
     nothing to hold or replay (compile-time proof).

Skipped unless protoc + g++ + pkg-config + libzmq + cppzmq are present, so
the host suite stays green; runs fully in the harpia Docker image:

    Docker/run.sh pytest UnitTests/test_critical_delivery_roundtrip.py
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
    out = tmp_path_factory.mktemp("harpia_critical_delivery")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    # the delivery runtime must have been copied beside the zmq headers,
    # since alarm_event is `critical` (D.3)
    assert os.path.isfile(os.path.join(cpp_root, "delivery", "harpia_delivery.h")), \
        "D.3 did not copy the delivery runtime into generated output"
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
    # no -Werror here: this links the real protoc-generated *.pb.cc, which is
    # not warning-clean under -Wextra. The delivery runtime's own -Werror
    # gate is test_delivery_runtime.py; correctness here is the static_asserts
    # + the runtime exit codes.
    cmd = ["g++", "-std=c++17",
           "-I", built["cpp_root"], *_pkgconfig("--cflags"),
           prog, *pb_ccs, "-o", binary, *_pkgconfig("--libs")]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return subprocess.run([binary], capture_output=True, text=True,
                          timeout=timeout)


# The subscription-propagation settle after a SUB connects to a bound PUB.
# alarm_event is `critical event` -> PUB/SUB, which has the classic ZMQ
# "slow joiner": a PUB drops anything sent before the SUB's subscription
# has reached it. flush() cannot be retried (it drains the queue), so the
# SUB must be ready first. 300ms on loopback is ~1000x the real propagation
# time -- bump only if a loaded CI box proves flaky.
_SETTLE_MS = 300


def test_critical_held_then_replayed_in_order(built):
    src = '''
#include "zmq/alarm_event_{h}_zmq.h"
#include <chrono>
#include <thread>

int main() {{
    ::zmq::context_t ctx{{1}};
    harpia::zmq_transport::alarm_event_publisher pub(ctx, "tcp://127.0.0.1:*");
    pub.socket().set(::zmq::sockopt::linger, 0);
    std::string endpoint = pub.socket().get(::zmq::sockopt::last_endpoint);

    // --- transport "stalled": subscriber absent. publish 5 -- each call
    //     only enqueues, the socket is never touched. ---
    for (int i = 1; i <= 5; ++i) {{
        ::alarm_event m;
        m.set_alarm_type("apnea");
        m.set_severity(i);
        auto out = pub.publish(m);
        if (!out.has_value()) return 10;                       // serialized fine
        if (*out != harpia::delivery::PushOutcome::Accepted) return 11;
    }}
    if (pub.pending() != 5) return 12;                          // all held

    // --- subscriber joins; let the subscription propagate ---
    harpia::zmq_transport::alarm_event_subscriber sub(ctx, endpoint);
    sub.socket().set(::zmq::sockopt::linger, 0);
    sub.socket().set(::zmq::sockopt::rcvtimeo, 3000);
    std::this_thread::sleep_for(std::chrono::milliseconds({settle}));

    // --- "reconnect": drain. all 5 go on the wire, none left behind ---
    if (pub.flush() != 5) return 13;
    if (pub.pending() != 0) return 14;

    // --- received in FIFO / seq order ---
    for (int i = 1; i <= 5; ++i) {{
        ::alarm_event in;
        if (!sub.receive(&in)) return 15;
        if (in.severity() != i) return 16;
    }}
    return 0;
}}
'''.format(h=HASH, settle=_SETTLE_MS)
    run = _build_and_run(built, "critical_replay", src, ["alarm_event"])
    assert run.returncode == 0, \
        "held/replay check failed at #{}\n{}".format(run.returncode, run.stderr)


def test_critical_overflow_rotates_oldest_and_audits(built):
    src = '''
#include "zmq/alarm_event_{h}_zmq.h"
#include <chrono>
#include <string>
#include <thread>

// Counts "queue_rotated" records so the test can prove a bounded-queue
// overrun is audited, never a silent drop. Same shape as the CountingSink
// in test_delivery_runtime.py.
struct CountingSink : harpia::compliance::AuditSink {{
    int rotated = 0;
    std::string last_detail;
    void record(const std::string& op, const std::string& /*subject*/,
                const std::string& detail = "") override {{
        if (op == "queue_rotated") ++rotated;
        last_detail = detail;
    }}
}};

int main() {{
    ::zmq::context_t ctx{{1}};
    CountingSink sink;
    // capacity 4, deliberately smaller than the burst
    harpia::zmq_transport::alarm_event_publisher pub(ctx, "tcp://127.0.0.1:*", 4, sink);
    pub.socket().set(::zmq::sockopt::linger, 0);
    std::string endpoint = pub.socket().get(::zmq::sockopt::last_endpoint);

    // --- 10 criticals produced while "stalled", queue holds 4 ---
    for (int i = 1; i <= 10; ++i) {{
        ::alarm_event m;
        m.set_severity(i);
        pub.publish(m);
    }}
    if (sink.rotated != 6) return 20;                   // 10 - capacity 4
    if (pub.queue().rotations() != 6) return 21;
    if (pub.pending() != 4) return 22;                  // never grew past capacity
    if (sink.last_detail != "dropped_seq=6") return 23; // seq 1..6 rotated out

    // --- reconnect + drain: survivors are the NEWEST 4, in order ---
    harpia::zmq_transport::alarm_event_subscriber sub(ctx, endpoint);
    sub.socket().set(::zmq::sockopt::linger, 0);
    sub.socket().set(::zmq::sockopt::rcvtimeo, 3000);
    std::this_thread::sleep_for(std::chrono::milliseconds({settle}));

    if (pub.flush() != 4) return 24;
    for (int expect = 7; expect <= 10; ++expect) {{
        ::alarm_event in;
        if (!sub.receive(&in)) return 25;
        if (in.severity() != expect) return 26;
    }}
    return 0;
}}
'''.format(h=HASH, settle=_SETTLE_MS)
    run = _build_and_run(built, "critical_overflow", src, ["alarm_event"])
    assert run.returncode == 0, \
        "overflow/rotate check failed at #{}\n{}".format(run.returncode, run.stderr)


def test_noncritical_sender_has_no_delivery_queue(built):
    """`courier` is a plain `push message` -- non-`critical`. Its generated
    sender keeps the direct `bool send()` API and has no queue: there is
    structurally nothing to hold across an outage and nothing to replay.
    The static_asserts are the assertion (the positive side -- that the
    critical publisher DOES have flush()/pending()/queue() -- is exercised
    for real by the two tests above). main() just confirms send() is the
    synchronous bool-returning call it always was.

    Only the `courier` header is included: two generated *_zmq.h in one
    translation unit collide on the shared `runtime_origin_id()` helper (a
    pre-existing one-header-per-TU limitation), so the contrast is made by
    detection traits on `courier_sender` alone.
    """
    src = '''
#include "zmq/courier_{h}_zmq.h"
#include <type_traits>
#include <utility>

template <class T, class = void> struct has_flush : std::false_type {{}};
template <class T>
struct has_flush<T, std::void_t<decltype(std::declval<T&>().flush())>>
    : std::true_type {{}};

template <class T, class = void> struct has_pending : std::false_type {{}};
template <class T>
struct has_pending<T, std::void_t<decltype(std::declval<const T&>().pending())>>
    : std::true_type {{}};

template <class T, class = void> struct has_queue : std::false_type {{}};
template <class T>
struct has_queue<T, std::void_t<decltype(std::declval<T&>().queue())>>
    : std::true_type {{}};

using courier_sender = harpia::zmq_transport::courier_sender;

// non-critical sender: no delivery-queue surface at all -- nothing to hold
// across an outage, nothing to replay.
static_assert(!has_flush<courier_sender>::value,
              "non-critical sender has no queue to flush");
static_assert(!has_pending<courier_sender>::value,
              "non-critical sender holds nothing -- it cannot 'pend'");
static_assert(!has_queue<courier_sender>::value,
              "non-critical sender exposes no BoundedQueue");

int main() {{
    ::zmq::context_t ctx{{1}};
    courier_sender snd(ctx, "tcp://127.0.0.1:5561");
    snd.socket().set(::zmq::sockopt::linger, 0);
    snd.socket().set(::zmq::sockopt::sndtimeo, 200);

    ::courier m;
    m.set_payload("routine-telemetry");
    // send() returns a plain bool and returns straight away -- the message
    // is handed to the socket, not parked in a queue for a later flush.
    static_assert(std::is_same<decltype(snd.send(m)), bool>::value,
                  "non-critical send() stays bool");
    (void)snd.send(m);
    return 0;
}}
'''.format(h=HASH)
    run = _build_and_run(built, "noncritical_no_queue", src, ["courier"])
    assert run.returncode == 0, \
        "non-critical contrast failed at #{}\n{}".format(run.returncode, run.stderr)
