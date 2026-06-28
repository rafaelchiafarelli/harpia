"""Stage 13 (ZMQ) test -- the generated transport is real, compilable, and
actually moves a message over a socket.

After the front-end + Stage 7 (message C++) + the ZMQ generator, this:
  - compiles every generated transport header (forcing the inline send/recv/
    publish/receive bodies to compile against real protobuf + cppzmq), and
  - builds, links and RUNS an inproc PUSH/PULL round-trip for `users`:
    sender.send(msg) -> receiver.recv(&msg) over a real zmq socket, asserting the
    fields survive serialization + transport.

Skipped unless protoc + g++ + pkg-config + libzmq + cppzmq (zmq.hpp) are present,
so the host suite stays green; inside the harpia Docker image it runs fully:

    docker/run.sh pytest tests/test_stage13_zmq.py
"""
import glob
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")

HASH = "734126ee6efdfbd64a1678bf49ee9683"


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

# method to exercise for each generated class suffix
_CALLS = {
    "sender": "    {{ harpia::zmq_transport::{cls} x(ctx, \"inproc://a\"); (void)x.send(m); }}\n",
    "receiver": "    {{ harpia::zmq_transport::{cls} x(ctx, \"inproc://b\"); (void)x.recv(&m); }}\n",
    "publisher": "    {{ harpia::zmq_transport::{cls} x(ctx, \"inproc://c\"); (void)x.publish(m); }}\n",
    "subscriber": "    {{ harpia::zmq_transport::{cls} x(ctx, \"inproc://d\"); (void)x.receive(&m); }}\n",
}


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_zmq")
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


def _classes(header_path):
    with open(header_path) as f:
        return re.findall(r"^class (\w+)_(sender|receiver|publisher|subscriber)",
                          f.read(), re.MULTILINE)


def test_every_zmq_adapter_compiles(built):
    adapters = sorted(glob.glob(os.path.join(built["zmq_dir"], "*_zmq.h")))
    assert adapters, "no ZMQ transports generated"
    cflags = _pkgconfig("--cflags")
    for adapter in adapters:
        name = os.path.basename(adapter)[:-len("_{}_zmq.h".format(HASH))]
        classes = _classes(adapter)
        calls = "".join(
            _CALLS[suffix].format(cls="{}_{}".format(base, suffix))
            for base, suffix in classes
        )
        tu = os.path.join(built["tmp"], "use_{}.cc".format(name))
        with open(tu, "w") as f:
            f.write(
                '#include "zmq/{}"\n'.format(os.path.basename(adapter)) +
                "void use(::zmq::context_t& ctx) {{\n"
                "    ::{name} m;\n".format(name=name) +
                calls +
                "}\n"
            )
        r = subprocess.run(
            ["g++", "-std=c++17", "-I", built["cpp_root"], *cflags,
             "-c", tu, "-o", os.devnull],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "{} transport failed to compile:\n{}".format(
            name, r.stderr)


def test_zmq_pushpull_roundtrip_runs(built):
    """Send a `users` message PUSH->PULL over a real inproc zmq socket."""
    adapter = "users_{}_zmq.h".format(HASH)
    assert os.path.exists(os.path.join(built["zmq_dir"], adapter)), \
        "users transport missing"

    prog = os.path.join(built["tmp"], "zmq_roundtrip.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "zmq/{adapter}"\n'
            "int main() {{\n"
            "    ::zmq::context_t ctx{{1}};\n"
            "    // bind the receiver first so the inproc endpoint exists\n"
            '    harpia::zmq_transport::users_receiver rcv(ctx, "inproc://users");\n'
            '    harpia::zmq_transport::users_sender   snd(ctx, "inproc://users");\n'
            "    ::users out;\n"
            '    out.set_name("neo");\n'
            '    out.set_address("matrix");\n'
            "    if (!snd.send(out)) return 1;\n"
            "    ::users in;\n"
            "    if (!rcv.recv(&in)) return 2;\n"
            '    if (in.name() != "neo" || in.address() != "matrix") return 3;\n'
            "    // originator stamped by the sender (process.md 1.3.1.1)\n"
            "    if (in.originator_{h}() !=\n"
            "        harpia::zmq_transport::users_sender::origin_id()) return 4;\n"
            "    if (in.originator_{h}().empty()) return 5;\n"
            "    return 0;\n"
            "}}\n".format(adapter=adapter, h=HASH)
        )

    pb_cc = os.path.join(built["proto_dir"], "users_{}.pb.cc".format(HASH))
    binary = os.path.join(built["tmp"], "zmq_roundtrip")
    cmd = ["g++", "-std=c++17", "-I", built["cpp_root"],
           *_pkgconfig("--cflags"), prog, pb_cc, "-o", binary,
           *_pkgconfig("--libs")]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "zmq round-trip failed to build:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "zmq round-trip failed at check #{}".format(
        run.returncode)
