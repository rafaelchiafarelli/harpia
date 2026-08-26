"""Integration tests for plans/message-versioning.md S5's gRPC capability
handshake (the "prove the pattern once" transport, per the plan's own slice
order -- REST/SOAP/ZMQ are separate, not-yet-built slices).

Covers, over a real (in-process) gRPC channel:
  - harpia::capability::negotiate() gets back the server's real advertised
    message-type set (GrpcCapabilityAdapter's generated capabilities_service).
  - a peer that never registered capabilities_service at all (a genuinely
    pre-feature legacy peer) resolves to the named "legacy peer" outcome --
    on_legacy_peer fires exactly once, negotiate() returns std::nullopt, and
    this completes within the deadline rather than hanging.
  - harpia::capability::Dispatcher routes a covered type to its handler and
    an uncovered type (or a covered type with no registered handler) to the
    mandatory fallback -- never a silent no-op.

Skipped unless protoc + grpc_cpp_plugin + g++ + pkg-config(grpc++) are
present, so the host suite stays green; runs fully in the harpia Docker
image:

    Docker/run.sh pytest UnitTests/test_message_versioning_capability.py
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


def _have_grpcpp():
    return subprocess.run(["pkg-config", "--exists", "grpc++"]).returncode == 0


pytestmark = pytest.mark.skipif(
    shutil.which("protoc") is None
    or shutil.which("grpc_cpp_plugin") is None
    or shutil.which("g++") is None
    or shutil.which("pkg-config") is None
    or not _have_grpcpp(),
    reason="needs protoc + grpc_cpp_plugin + g++ + grpc++ (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_capability")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    from ProtoFile.GrpcCompiler import GrpcCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    assert GrpcCompiler(dest=build).Process() is None, "Stage 13 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")
    cap_dir = os.path.join(cpp_root, "capability")

    cap_headers = glob.glob(os.path.join(cap_dir, "capabilities_*_grpc.h"))
    assert cap_headers, "no capabilities_<hash>_grpc.h generated"
    m = re.match(r"^capabilities_([0-9a-f]+)_grpc\.h$",
                os.path.basename(cap_headers[0]))
    assert m, "unexpected capability header name " + cap_headers[0]
    root_hash = m.group(1)

    return {
        "cpp_root": cpp_root,
        "proto_dir": proto_dir,
        "cap_dir": cap_dir,
        "root_hash": root_hash,
        "tmp": str(out),
    }


def _cap_objs(built):
    proto = built["proto_dir"]
    return [
        os.path.join(proto, "capabilities_service.pb.cc"),
        os.path.join(proto, "capabilities_service.grpc.pb.cc"),
    ]


def _build_and_run(built, tmp_path, prog_text, name, extra_objs=()):
    prog = tmp_path / "{}.cc".format(name)
    prog.write_text(prog_text, encoding="utf-8")
    binary = str(tmp_path / name)
    cmd = ["g++", "-std=c++17", "-I", built["cpp_root"],
           *_pkgconfig("--cflags"), str(prog), *_cap_objs(built), *extra_objs,
           "-o", binary, *_pkgconfig("--libs"), "-lpthread"]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return subprocess.run([binary], capture_output=True, text=True)


def test_negotiate_gets_real_capability_set(built, tmp_path):
    r = _build_and_run(built, tmp_path, '''
#include "capability/capabilities_{h}_grpc.h"
#include "capability/harpia_capability.h"
#include <grpcpp/grpcpp.h>
#include <chrono>
int main() {{
    harpia::grpc_svc::capabilities_service svc;
    ::grpc::ServerBuilder b;
    b.RegisterService(&svc);
    auto server = b.BuildAndStart();
    if (!server) return 1;
    auto chan = server->InProcessChannel(::grpc::ChannelArguments());

    bool legacy_fired = false;
    auto types = harpia::capability::negotiate(
        chan, std::chrono::milliseconds(2000), [&]{{ legacy_fired = true; }});
    if (legacy_fired) return 2;
    if (!types) return 3;
    if (types->count("users") == 0) return 4;   // a real message from the schema
    if (types->count("no_such_message") != 0) return 5;
    return 0;
}}
'''.format(h=built["root_hash"]), "negotiate_ok")
    assert r.returncode == 0, "exit {} (2=legacy fired, 3=nullopt, 4/5=wrong set)".format(
        r.returncode)


def test_negotiate_legacy_peer_is_a_named_outcome_not_a_hang(built, tmp_path):
    """A real generated-project server that has OTHER services registered
    (prince_Service, here) but predates capabilities_service entirely is
    exactly the pre-feature legacy peer this plan calls for: the RPC comes
    back UNIMPLEMENTED immediately (no need to even wait out the deadline),
    on_legacy_peer fires exactly once, negotiate() returns nullopt -- not an
    error, not a hang. (A server with literally zero services registered
    isn't a valid gRPC server -- BuildAndStart() itself fails -- so
    "prince_Service only" is the realistic legacy-peer shape.)"""
    prince_proto_h = "protofiles/prince_{h}_service.grpc.pb.h".format(h=built["root_hash"])
    r = _build_and_run(built, tmp_path, '''
#include "{prince_h}"
#include "capability/harpia_capability.h"
#include <grpcpp/grpcpp.h>
#include <chrono>

class PrinceImpl final
    : public ::frameworkProtos::prince_Service::Service {{}};

int main() {{
    // prince_Service registered, capabilities_service is NOT -- a real
    // pre-feature-generated peer, not just an empty server.
    PrinceImpl prince;
    ::grpc::ServerBuilder b;
    b.RegisterService(&prince);
    auto server = b.BuildAndStart();
    if (!server) return 1;
    auto chan = server->InProcessChannel(::grpc::ChannelArguments());

    int legacy_fires = 0;
    auto types = harpia::capability::negotiate(
        chan, std::chrono::milliseconds(2000), [&]{{ ++legacy_fires; }});
    if (types) return 2;              // must be nullopt
    if (legacy_fires != 1) return 3;  // exactly once
    return 0;
}}
'''.format(prince_h=prince_proto_h, h=built["root_hash"]), "negotiate_legacy",
        extra_objs=[
            os.path.join(built["proto_dir"], "prince_{}_service.grpc.pb.cc".format(built["root_hash"])),
            os.path.join(built["proto_dir"], "prince_{}_service.pb.cc".format(built["root_hash"])),
            os.path.join(built["proto_dir"], "prince_{}.pb.cc".format(built["root_hash"])),
            os.path.join(built["proto_dir"], "errorCode.pb.cc"),
            os.path.join(built["proto_dir"], "heartBeat.pb.cc"),
        ])
    assert r.returncode == 0, "exit {} (2=got a set from a legacy peer, 3=hook fired wrong # times)".format(
        r.returncode)


def test_dispatcher_routes_covered_type_to_its_handler(built, tmp_path):
    r = _build_and_run(built, tmp_path, '''
#include "capability/harpia_capability_dispatch.h"
#include <set>
#include <string>
int main() {
    int handler_calls = 0, fallback_calls = 0;
    harpia::capability::Dispatcher d(
        [&](const std::string&) { ++fallback_calls; });
    d.on("TypeA", [&](const std::string&) { ++handler_calls; });

    std::set<std::string> peer = {"TypeA", "TypeB"};
    d.dispatch("TypeA", peer);
    if (handler_calls != 1) return 1;
    if (fallback_calls != 0) return 2;
    return 0;
}
''', "dispatch_covered")
    assert r.returncode == 0, "exit {}".format(r.returncode)


def test_dispatcher_falls_back_never_silently(built, tmp_path):
    """Both an uncovered type (not in the peer's set) and a covered type with
    no registered handler must reach the fallback -- never a silent no-op."""
    r = _build_and_run(built, tmp_path, '''
#include "capability/harpia_capability_dispatch.h"
#include <set>
#include <string>
#include <vector>
int main() {
    std::vector<std::string> fallback_calls;
    harpia::capability::Dispatcher d(
        [&](const std::string& t) { fallback_calls.push_back(t); });
    d.on("TypeA", [](const std::string&) {});

    std::set<std::string> peer = {"TypeA", "TypeB"};
    d.dispatch("TypeC", peer);   // not in peer's set at all
    d.dispatch("TypeB", peer);   // in peer's set, but no handler registered

    if (fallback_calls.size() != 2) return 1;
    if (fallback_calls[0] != "TypeC") return 2;
    if (fallback_calls[1] != "TypeB") return 3;
    return 0;
}
''', "dispatch_fallback")
    assert r.returncode == 0, "exit {}".format(r.returncode)
