"""transport-multipeer-coverage / zmq-multipeer task 2 -- PUSH/PULL
load-balance, same language (C++).

Same gap as task 1 (`test_zmq_pubsub_fanout.py`) but for the other ZMQ
topology: the generated transport is only ever proven 1-sender-to-1-receiver
elsewhere. This drives one `courier_sender` (push-only,
`HarpiaTest/Include/file3.harpia`) round-robining real, separate messages
across **3** `courier_receiver` instances over real `tcp://` sockets.

Per `ZmqAdapter/CLAUDE.md`'s documented roles, PULL receivers `bind` and the
PUSH sender `connect`s -- so each receiver binds its own ephemeral endpoint
first, then the sender's constructor connects to the first and its raw
`socket()` is handed two more `connect()` calls for the other two (standard
ZMQ fan-out-the-connections shape for a PUSH socket load-balancing across
several bound PULL peers).

Skipped unless protoc + g++ + pkg-config + libzmq + cppzmq are present, so
the host suite stays green; runs fully in the harpia Docker image:

    Docker/run.sh pytest UnitTests/test_zmq_pushpull_loadbalance.py
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
    out = tmp_path_factory.mktemp("harpia_zmq_pushpull_loadbalance")
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


def test_three_pullers_split_the_work_no_loss_no_duplicates(built):
    adapter = "courier_{}_zmq.h".format(HASH)
    assert os.path.exists(os.path.join(built["zmq_dir"], adapter)), \
        "courier transport missing"

    src = '''
#include "zmq/courier_{h}_zmq.h"
#include <chrono>
#include <cstdio>
#include <set>
#include <thread>

int main() {{
    ::zmq::context_t ctx{{1}};

    harpia::zmq_transport::courier_receiver r1(ctx, "tcp://127.0.0.1:*");
    harpia::zmq_transport::courier_receiver r2(ctx, "tcp://127.0.0.1:*");
    harpia::zmq_transport::courier_receiver r3(ctx, "tcp://127.0.0.1:*");
    harpia::zmq_transport::courier_receiver* receivers[3] = {{&r1, &r2, &r3}};
    std::string endpoints[3];
    for (int i = 0; i < 3; ++i) {{
        receivers[i]->socket().set(::zmq::sockopt::linger, 0);
        endpoints[i] = receivers[i]->socket().get(::zmq::sockopt::last_endpoint);
    }}

    // PUSH sender: ctor connects to the first puller, two more connect()
    // calls on the raw socket fan it out to the other two (ZmqAdapter/CLAUDE.md:
    // "PUSH sender connects+send, PULL receiver binds+recv").
    harpia::zmq_transport::courier_sender snd(ctx, endpoints[0]);
    snd.socket().set(::zmq::sockopt::linger, 0);
    snd.socket().connect(endpoints[1]);
    snd.socket().connect(endpoints[2]);

    // let all three connections actually establish before the round-robin
    // starts, same settle rationale as the PUB/SUB slow-joiner elsewhere.
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    const int kN = 30;
    for (int i = 1; i <= kN; ++i) {{
        ::courier m;
        m.set_payload("seq-" + std::to_string(i));
        if (!snd.send(m)) return 1;
    }}

    // Drain each puller until it times out (no more messages for it),
    // tracking counts and the set of sequence numbers actually seen.
    std::set<int> seen;
    int per_puller[3] = {{0, 0, 0}};
    for (int i = 0; i < 3; ++i) {{
        receivers[i]->socket().set(::zmq::sockopt::rcvtimeo, 500);
        for (;;) {{
            ::courier in;
            if (!receivers[i]->recv(&in)) break;  // timed out -- this puller is done
            int seq = std::atoi(in.payload().c_str() + 4);  // "seq-<N>"
            if (!seen.insert(seq).second) return 2;         // duplicate across pullers
            ++per_puller[i];
        }}
    }}

    if ((int)seen.size() != kN) return 3;              // lost or short
    for (int s = 1; s <= kN; ++s) {{
        if (seen.find(s) == seen.end()) return 4;      // exact union check
    }}
    for (int i = 0; i < 3; ++i) {{
        if (per_puller[i] == 0) return 5;              // work actually distributed
        if (per_puller[i] == kN) return 6;             // didn't silently serialize onto one
    }}
    return 0;
}}
'''.format(h=HASH)
    run = _build_and_run(built, "pushpull_loadbalance", src, ["courier"])
    assert run.returncode == 0, \
        "load-balance check failed at #{}\n{}".format(run.returncode, run.stderr)
