"""Stage 13 test -- the generated gRPC stubs are real, compilable, linkable C++.

After the front-end + Stage 7 (message C++) + Stage 13 (gRPC stubs), this:
  - compiles every generated <name>_service.grpc.pb.cc against grpc++ (proves all
    12 service stubs are well-formed), and
  - builds, links and RUNS a program that instantiates the generated client Stub
    (prince_Service::NewStub) and a server Service skeleton subclass -- proving
    the push/pullByID/streamSrc/heartBeat interface is usable end to end.

Skipped unless protoc + grpc_cpp_plugin + g++ + pkg-config(grpc++) are present,
so the host suite stays green; inside the harpia Docker image it runs fully:

    Docker/run.sh pytest UnitTests/test_stage13.py
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

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"


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
    # transport-authn task 4: this test exercises the flat x-user/x-pswd
    # metadata gate, which is the variant emitted when the compliance profile
    # does NOT mandate hardened transport. Pin a low-risk profile so RBAC stays
    # compiled out (the RBAC gate has its own end-to-end test,
    # UnitTests/test_rbac.py).
    cfg = os.path.join(str(out), "low_risk.harpia.yaml")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write("risk_class: class_a\ntopology: standalone\n")
    env = {**os.environ, "HARPIA_COMPLIANCE_CONFIG": cfg}
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True, env=env)
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


def test_grpc_service_impl_wires_crudl(built):
    """The generated gRPC service impl (users) calls the CRUDL DAO: push creates a
    row and pullByID reads it back. Invokes the RPC methods directly (ServerContext
    unused) so no server/wire is needed."""
    SQLITE = os.path.join(REPO_ROOT, "third_party", "sqlite")
    proto = built["proto_dir"]
    cpp_root = built["cpp_root"]


    prog = os.path.join(built["tmp"], "grpc_crudl.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "grpc/users_{h}_grpc.h"\n'
            "#include <soci/soci.h>\n"
            "#include <soci/sqlite3/soci-sqlite3.h>\n"
            "int main() {{\n"
            '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    harpia::grpc_svc::users_service svc(db);\n"
            "    ::frameworkProtos::users_Message req;\n"
            "    req.mutable_msg()->set_id_{h}(1);\n"
            '    req.mutable_msg()->set_name("neo");\n'
            "    ::frameworkProtos::errorCode ec;\n"
            "    if (!svc.push(nullptr, &req, &ec).ok() || ec.code() != 0) return 3;\n"
            "    ::frameworkProtos::users_ID id; id.set_id(1);\n"
            "    ::frameworkProtos::users_Message resp;\n"
            "    if (!svc.pullByID(nullptr, &id, &resp).ok()) return 4;\n"
            '    if (resp.msg().name() != "neo") return 5;\n'
            "    ::frameworkProtos::users_ID miss; miss.set_id(999);\n"
            "    ::frameworkProtos::users_Message r2;\n"
            "    if (svc.pullByID(nullptr, &miss, &r2).ok()) return 6;\n"
            "    return 0;\n"
            "}}\n".format(h=HASH)
        )

    pb = lambda n: os.path.join(proto, "{}.pb.cc".format(n))
    objs = [
        os.path.join(proto, "users_{}_service.grpc.pb.cc".format(HASH)),
        pb("users_{}_service".format(HASH)),
        pb("users_{}".format(HASH)),
        pb("errorCode"),
        pb("heartBeat"),
    ]
    binary = os.path.join(built["tmp"], "grpc_crudl")
    cmd = ["g++", "-std=c++17", "-I", cpp_root,
           *_pkgconfig("--cflags"), prog, *objs, "-o", binary,
           "-lsoci_core", "-lsoci_sqlite3",
           *_pkgconfig("--libs"), "-lpthread", "-ldl"]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "gRPC CRUDL program failed to build:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True)
    assert run.returncode == 0, "gRPC CRUDL wiring failed at check #{}".format(
        run.returncode)


def test_grpc_metadata_auth(built):
    """Over a real (in-process) gRPC channel, the data RPCs require the credential
    metadata (x-user/x-pswd): correct -> OK, absent/wrong -> UNAUTHENTICATED."""
    SQLITE = os.path.join(REPO_ROOT, "third_party", "sqlite")
    proto = built["proto_dir"]
    cpp_root = built["cpp_root"]


    prog = os.path.join(built["tmp"], "grpc_auth.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "grpc/users_{h}_grpc.h"\n'
            "#include <grpcpp/grpcpp.h>\n"
            "#include <soci/soci.h>\n"
            "#include <soci/sqlite3/soci-sqlite3.h>\n"
            "int main() {{\n"
            '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    harpia::grpc_svc::users_service svc(db);\n"
            "    ::grpc::ServerBuilder b;\n"
            "    b.RegisterService(&svc);\n"
            "    auto server = b.BuildAndStart();\n"
            "    if (!server) return 3;\n"
            "    auto chan = server->InProcessChannel(::grpc::ChannelArguments());\n"
            "    auto stub = ::frameworkProtos::users_Service::NewStub(chan);\n"
            "    auto run = [&]() -> int {{\n"
            "        ::frameworkProtos::users_Message req;\n"
            "        req.mutable_msg()->set_id_{h}(1);\n"
            '        req.mutable_msg()->set_name("neo");\n'
            "        ::grpc::ClientContext c1;\n"
            '        c1.AddMetadata("x-user", "users");\n'
            '        c1.AddMetadata("x-pswd", "{h}");\n'
            "        ::frameworkProtos::errorCode ec1;\n"
            "        auto s1 = stub->push(&c1, req, &ec1);\n"
            "        if (!s1.ok() || ec1.code() != 0) return 4;\n"
            "        ::grpc::ClientContext c2;\n"
            "        ::frameworkProtos::errorCode ec2;\n"
            "        auto s2 = stub->push(&c2, req, &ec2);\n"
            "        if (s2.error_code() != ::grpc::StatusCode::UNAUTHENTICATED) return 5;\n"
            "        ::grpc::ClientContext c3;\n"
            '        c3.AddMetadata("x-user", "users");\n'
            '        c3.AddMetadata("x-pswd", "nope");\n'
            "        ::frameworkProtos::users_ID id; id.set_id(1);\n"
            "        ::frameworkProtos::users_Message resp;\n"
            "        auto s3 = stub->pullByID(&c3, id, &resp);\n"
            "        if (s3.error_code() != ::grpc::StatusCode::UNAUTHENTICATED) return 6;\n"
            "        ::grpc::ClientContext c4;\n"
            '        c4.AddMetadata("x-user", "users");\n'
            '        c4.AddMetadata("x-pswd", "{h}");\n'
            "        ::frameworkProtos::users_Message resp2;\n"
            "        auto s4 = stub->pullByID(&c4, id, &resp2);\n"
            '        if (!s4.ok() || resp2.msg().name() != "neo") return 7;\n'
            "        return 0;\n"
            "    }};\n"
            "    const int code = run();\n"
            "    server->Shutdown();\n"
            "    return code;\n"
            "}}\n".format(h=HASH)
        )

    pb = lambda n: os.path.join(proto, "{}.pb.cc".format(n))
    objs = [
        os.path.join(proto, "users_{}_service.grpc.pb.cc".format(HASH)),
        pb("users_{}_service".format(HASH)),
        pb("users_{}".format(HASH)),
        pb("errorCode"),
        pb("heartBeat"),
    ]
    binary = os.path.join(built["tmp"], "grpc_auth")
    cmd = ["g++", "-std=c++17", "-I", cpp_root,
           *_pkgconfig("--cflags"), prog, *objs, "-o", binary,
           "-lsoci_core", "-lsoci_sqlite3",
           *_pkgconfig("--libs"), "-lpthread", "-ldl"]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "gRPC auth program failed to build:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "gRPC metadata auth failed at check #{}".format(
        run.returncode)


def test_grpc_streamsrc_pagination(built):
    """streamSrc honors the request's offset/limit (limit>0 -> paginated
    subset in order); limit<=0 (unset, proto3 default) still streams
    everything -- pre-pagination behavior unchanged."""
    proto = built["proto_dir"]
    cpp_root = built["cpp_root"]

    prog = os.path.join(built["tmp"], "grpc_page.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "grpc/users_{h}_grpc.h"\n'
            "#include <grpcpp/grpcpp.h>\n"
            "#include <soci/soci.h>\n"
            "#include <soci/sqlite3/soci-sqlite3.h>\n"
            "#include <vector>\n"
            "int main() {{\n"
            '    ::soci::session db(::soci::sqlite3, ":memory:");\n'
            "    harpia::db::users_dao dao(db);\n"
            "    if (!dao.create_table()) return 2;\n"
            "    harpia::grpc_svc::users_service svc(db);\n"
            "    ::grpc::ServerBuilder b;\n"
            "    b.RegisterService(&svc);\n"
            "    auto server = b.BuildAndStart();\n"
            "    if (!server) return 3;\n"
            "    auto chan = server->InProcessChannel(::grpc::ChannelArguments());\n"
            "    auto stub = ::frameworkProtos::users_Service::NewStub(chan);\n"
            "    auto run = [&]() -> int {{\n"
            "        for (int i = 1; i <= 5; ++i) {{\n"
            "            ::frameworkProtos::users_Message req;\n"
            "            req.mutable_msg()->set_id_{h}(i);\n"
            '            req.mutable_msg()->set_name("n" + std::to_string(i));\n'
            "            ::grpc::ClientContext c;\n"
            '            c.AddMetadata("x-user", "users");\n'
            '            c.AddMetadata("x-pswd", "{h}");\n'
            "            ::frameworkProtos::errorCode ec;\n"
            "            if (!stub->push(&c, req, &ec).ok() || ec.code() != 0) return 4;\n"
            "        }}\n"
            "        ::grpc::ClientContext cp;\n"
            '        cp.AddMetadata("x-user", "users");\n'
            '        cp.AddMetadata("x-pswd", "{h}");\n'
            "        ::frameworkProtos::users_Stream reqp;\n"
            "        reqp.set_offset(1); reqp.set_limit(2);\n"
            "        auto rp = stub->streamSrc(&cp, reqp);\n"
            "        std::vector<std::string> page;\n"
            "        ::frameworkProtos::users_Message m;\n"
            "        while (rp->Read(&m)) page.push_back(m.msg().name());\n"
            "        if (!rp->Finish().ok()) return 5;\n"
            '        if (page.size() != 2 || page[0] != "n2" || page[1] != "n3") return 6;\n'
            "        ::grpc::ClientContext ca;\n"
            '        ca.AddMetadata("x-user", "users");\n'
            '        ca.AddMetadata("x-pswd", "{h}");\n'
            "        ::frameworkProtos::users_Stream reqa;  // offset/limit unset (0)\n"
            "        auto ra = stub->streamSrc(&ca, reqa);\n"
            "        int count = 0;\n"
            "        ::frameworkProtos::users_Message m2;\n"
            "        while (ra->Read(&m2)) ++count;\n"
            "        if (!ra->Finish().ok() || count != 5) return 7;\n"
            "        return 0;\n"
            "    }};\n"
            "    const int code = run();\n"
            "    server->Shutdown();\n"
            "    return code;\n"
            "}}\n".format(h=HASH)
        )

    pb = lambda n: os.path.join(proto, "{}.pb.cc".format(n))
    objs = [
        os.path.join(proto, "users_{}_service.grpc.pb.cc".format(HASH)),
        pb("users_{}_service".format(HASH)),
        pb("users_{}".format(HASH)),
        pb("errorCode"),
        pb("heartBeat"),
    ]
    binary = os.path.join(built["tmp"], "grpc_page")
    cmd = ["g++", "-std=c++17", "-I", cpp_root,
           *_pkgconfig("--cflags"), prog, *objs, "-o", binary,
           "-lsoci_core", "-lsoci_sqlite3",
           *_pkgconfig("--libs"), "-lpthread", "-ldl"]
    c = subprocess.run(cmd, capture_output=True, text=True)
    assert c.returncode == 0, "gRPC streamSrc pagination program failed to build:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "gRPC streamSrc pagination failed at check #{}".format(
        run.returncode)
