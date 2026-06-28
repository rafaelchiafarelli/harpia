"""Stage 13 test -- the generated gRPC stubs are real, compilable, linkable C++.

After the front-end + Stage 7 (message C++) + Stage 13 (gRPC stubs), this:
  - compiles every generated <name>_service.grpc.pb.cc against grpc++ (proves all
    12 service stubs are well-formed), and
  - builds, links and RUNS a program that instantiates the generated client Stub
    (prince_Service::NewStub) and a server Service skeleton subclass -- proving
    the push/pullByID/streamSrc/heartBeat interface is usable end to end.

Skipped unless protoc + grpc_cpp_plugin + g++ + pkg-config(grpc++) are present,
so the host suite stays green; inside the harpia Docker image it runs fully:

    docker/run.sh pytest tests/test_stage13.py
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")

HASH = "734126ee6efdfbd64a1678bf49ee9683"


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
    # grpc++ pulls in the gRPC runtime; protobuf provides the message symbols
    # (typeinfo for Message, SpaceUsedLong, ...) the generated .pb.cc need.
    out = subprocess.run(["pkg-config", *args, "grpc++", "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_stage13")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    from ProtoFile.GrpcCompiler import GrpcCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    assert GrpcCompiler(dest=build).Process() is None, "Stage 13 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "cpp_root": cpp_root,
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tmp": str(out),
    }


def test_all_grpc_stubs_compile(built):
    stubs = sorted(glob.glob(os.path.join(built["proto_dir"], "*.grpc.pb.cc")))
    assert stubs, "no gRPC stubs generated"
    cflags = _pkgconfig("--cflags")
    for stub in stubs:
        r = subprocess.run(
            ["g++", "-std=c++17", "-I", built["cpp_root"], *cflags,
             "-c", stub, "-o", os.devnull],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "{} failed to compile:\n{}".format(
            os.path.basename(stub), r.stderr)


def test_grpc_interface_links_and_runs(built):
    """Instantiate the generated client Stub + server Service skeleton."""
    proto = built["proto_dir"]
    prog = os.path.join(built["tmp"], "grpc_use.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "protofiles/prince_{h}_service.grpc.pb.h"\n'
            "#include <grpcpp/grpcpp.h>\n"
            "\n"
            "// server skeleton: the generated Service base is concrete\n"
            "// (each RPC has a default UNIMPLEMENTED impl), so this subclass\n"
            "// proves the interface exists and is overridable.\n"
            "class PrinceImpl final\n"
            "    : public ::frameworkProtos::prince_Service::Service {{\n"
            "    ::grpc::Status push(::grpc::ServerContext*,\n"
            "                        const ::frameworkProtos::prince_Message*,\n"
            "                        ::frameworkProtos::errorCode*) override {{\n"
            "        return ::grpc::Status::OK;\n"
            "    }}\n"
            "}};\n"
            "\n"
            "int main() {{\n"
            "    auto chan = ::grpc::CreateChannel(\n"
            '        "localhost:50051", ::grpc::InsecureChannelCredentials());\n'
            "    auto stub = ::frameworkProtos::prince_Service::NewStub(chan);\n"
            "    PrinceImpl service;\n"
            "    return (stub && (&service != nullptr)) ? 0 : 1;\n"
            "}}\n".format(h=HASH)
        )

    # message code the service stub depends on (service proto imports these)
    pb = lambda n: os.path.join(proto, "{}.pb.cc".format(n))
    objs = [
        os.path.join(proto, "prince_{}_service.grpc.pb.cc".format(HASH)),
        pb("prince_{}_service".format(HASH)),
        pb("prince_{}".format(HASH)),
        pb("errorCode"),
        pb("heartBeat"),
    ]
    binary = os.path.join(built["tmp"], "grpc_use")
    cmd = ["g++", "-std=c++17", "-I", built["cpp_root"],
           *_pkgconfig("--cflags"), prog, *objs, "-o", binary,
           *_pkgconfig("--libs")]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "gRPC program failed to build/link:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True)
    assert run.returncode == 0, "gRPC program returned {}".format(run.returncode)
