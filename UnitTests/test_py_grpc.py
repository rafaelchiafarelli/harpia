"""python-target / py-transports-http task 4: generated gRPC servicers
(``harpia_generated/grpc/*_grpc.py`` over ``harpia_runtime.grpc_service``)
on an insecure ``grpc.server`` (``PlainGrpc``; the bring-up needs mTLS
here because the fixture has ``protected`` messages).

Low-risk profile (flat ``x-user`` / ``x-pswd`` metadata). Image-gated:
- the servicer set equals the C++ ``grpc/*_grpc.h`` set;
- ``push`` → ``errorCode 0 "ok"`` (duplicate → ``1 "create failed"``),
  ``pullByID`` → the row / ``NOT_FOUND``, ``streamSrc`` → every row and one
  page (``offset`` / ``limit``), ``heartBeat`` echoes without metadata;
- data RPCs without / with wrong metadata → ``UNAUTHENTICATED``;
- a held pool of 1 → ``RESOURCE_EXHAUSTED "db pool exhausted"``.
protoc + g++ + grpc++: a C++ client built from the generated stubs calls
``push`` / ``pullByID`` / ``streamSrc`` on the Python server.
"""
import importlib
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests.test_py_rest import generate_low_risk  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
MD = (("x-user", "users"), ("x-pswd", HASH))


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("py_grpc")
    os.makedirs(os.path.join(str(tmp), "out"))
    g = generate_low_risk(tmp)
    P.fixture_messages(P.py_root(g))
    return g


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


def _server(tmp_path, size=4, timeout=5.0):
    pool = _mod("harpia_runtime.db.pool").sqlite_pool(str(tmp_path / "g.db"), size=size,
                                                       borrow_timeout_s=timeout)
    with pool.borrow() as conn:
        _mod("harpia_generated.db.users_{h}_dao").users_dao(conn).create_table()
    return PlainGrpc(pool), pool


class PlainGrpc:
    """The ``users`` servicer on an insecure ``grpc.server``. Not the generated
    ``GrpcServer``: the fixture's ``protected`` messages make its bring-up
    require mTLS even under a low-risk profile (its own test covers that)."""

    def __init__(self, pool):
        from concurrent.futures import ThreadPoolExecutor
        import grpc
        mod = _mod("harpia_generated.grpc.users_{h}_grpc")
        self.server = grpc.server(ThreadPoolExecutor(max_workers=8))
        mod.add_to_server(mod.users_Service(pool), self.server)
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()

    def stop(self):
        self.server.stop(None).wait()


def _stub(port):
    import grpc
    ch = grpc.insecure_channel("127.0.0.1:%d" % port)
    return ch, _mod("harpia_generated.protofiles.users_{h}_service_pb2_grpc").users_ServiceStub(ch)


def _svc():
    return _mod("harpia_generated.protofiles.users_{h}_service_pb2")


def _push(stub, pk, name, md=MD):
    m = _svc().users_Message()
    setattr(m.msg, PK, pk)
    m.msg.name = name
    return stub.push(m, metadata=md)


def test_servicer_set_matches_cpp(gen):
    cpp = {f[:-len("_grpc.h")] for f in os.listdir(os.path.join(gen, "generated", "cpp", "grpc"))
           if f.endswith("_grpc.h")}
    py = {f[:-len("_grpc.py")] for f in os.listdir(os.path.join(P.py_root(gen),
                                                                 "harpia_generated", "grpc"))
          if f.endswith("_grpc.py")}
    assert py == cpp and cpp


def test_rpcs(gen, tmp_path):
    import grpc
    srv, _ = _server(tmp_path)
    ch, stub = _stub(srv.port)
    try:
        for i in range(1, 6):
            r = _push(stub, i, "n%d" % i)
            assert (r.code, r.message) == (0, "ok")
        r = _push(stub, 1, "dup")
        assert (r.code, r.message) == (1, "create failed")
        got = stub.pullByID(_svc().users_ID(id=3), metadata=MD)
        assert got.msg.name == "n3"
        with pytest.raises(grpc.RpcError) as e:
            stub.pullByID(_svc().users_ID(id=99), metadata=MD)
        assert e.value.code() == grpc.StatusCode.NOT_FOUND and e.value.details() == "not found"
        names = [m.msg.name for m in stub.streamSrc(_svc().users_Stream(), metadata=MD)]
        assert names == ["n1", "n2", "n3", "n4", "n5"]
        page = [m.msg.name for m in stub.streamSrc(_svc().users_Stream(offset=1, limit=2),
                                                   metadata=MD)]
        assert page == ["n2", "n3"]
        hb = _svc().users_HeartBeat()
        assert stub.heartBeat(hb) == hb  # never gated
    finally:
        ch.close()
        srv.stop()


@pytest.mark.parametrize("md", [None, (("x-user", "users"), ("x-pswd", "nope")),
                                (("x-user", "data"), ("x-pswd", HASH))])
def test_unauthenticated(md, gen, tmp_path):
    import grpc
    srv, _ = _server(tmp_path)
    ch, stub = _stub(srv.port)
    try:
        for call in (lambda: _push(stub, 1, "x", md),
                     lambda: stub.pullByID(_svc().users_ID(id=1), metadata=md),
                     lambda: list(stub.streamSrc(_svc().users_Stream(), metadata=md))):
            with pytest.raises(grpc.RpcError) as e:
                call()
            assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
            assert e.value.details() == "unauthorized"
    finally:
        ch.close()
        srv.stop()


def test_pool_exhausted(gen, tmp_path):
    import grpc
    srv, pool = _server(tmp_path, size=1, timeout=0.2)
    ch, stub = _stub(srv.port)
    try:
        with pool.borrow():
            with pytest.raises(grpc.RpcError) as e:
                stub.pullByID(_svc().users_ID(id=1), metadata=MD)
        assert e.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
        assert e.value.details() == "db pool exhausted"
    finally:
        ch.close()
        srv.stop()


_CPP = r'''
#include <cstdio>
#include <grpcpp/grpcpp.h>
#include "protofiles/users_%(h)s_service.grpc.pb.h"
int main(int, char** argv) {
    auto ch = ::grpc::CreateChannel(argv[1], ::grpc::InsecureChannelCredentials());
    auto stub = ::frameworkProtos::users_Service::NewStub(ch);
    auto md = [](::grpc::ClientContext& c) {
        c.AddMetadata("x-user", "users"); c.AddMetadata("x-pswd", "%(h)s"); };
    { ::grpc::ClientContext c; md(c);
      ::frameworkProtos::users_Message m; m.mutable_msg()->set_id_%(h)s(11);
      m.mutable_msg()->set_name("from-cpp");
      ::frameworkProtos::errorCode r;
      auto s = stub->push(&c, m, &r);
      std::printf("push %%d %%d %%s\n", (int)s.error_code(), r.code(), r.message().c_str()); }
    { ::grpc::ClientContext c; md(c);
      ::frameworkProtos::users_ID id; id.set_id(11);
      ::frameworkProtos::users_Message r;
      auto s = stub->pullByID(&c, id, &r);
      std::printf("pull %%d %%s\n", (int)s.error_code(), r.msg().name().c_str()); }
    { ::grpc::ClientContext c; md(c);
      ::frameworkProtos::users_Stream req;
      auto reader = stub->streamSrc(&c, req);
      ::frameworkProtos::users_Message m; int n = 0;
      while (reader->Read(&m)) ++n;
      auto s = reader->Finish();
      std::printf("stream %%d %%d\n", (int)s.error_code(), n); }
    { ::grpc::ClientContext c;
      ::frameworkProtos::users_ID id; id.set_id(11);
      ::frameworkProtos::users_Message r;
      std::printf("anon %%d\n", (int)stub->pullByID(&c, id, &r).error_code()); }
    return 0;
}
'''


@pytest.mark.skipif(shutil.which("g++") is None or shutil.which("pkg-config") is None,
                    reason="needs g++ + grpc++")
def test_cpp_client_calls_python_server(gen, tmp_path):
    cpp_root = os.path.join(gen, "generated", "cpp")
    pf = os.path.join(cpp_root, "protofiles")
    srcs = [os.path.join(pf, f) for f in (
        "users_{}.pb.cc".format(HASH), "users_{}_service.pb.cc".format(HASH),
        "users_{}_service.grpc.pb.cc".format(HASH), "errorCode.pb.cc", "heartBeat.pb.cc")]
    missing = [s for s in srcs if not os.path.exists(s)]
    if missing:
        pytest.skip("no C++ gRPC stubs generated: %s" % missing)
    (tmp_path / "c.cpp").write_text(_CPP % {"h": HASH})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "grpc++", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "c"
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(tmp_path / "c.cpp"), *srcs,
                        "-o", str(exe), *flags, "-lpthread"],
                       capture_output=True, text=True, timeout=900)
    assert c.returncode == 0, c.stderr[-3000:]
    srv, _ = _server(tmp_path)
    try:
        out = subprocess.run([str(exe), "127.0.0.1:%d" % srv.port], capture_output=True,
                             text=True, timeout=60, check=True).stdout.splitlines()
    finally:
        srv.stop()
    assert out == ["push 0 0 ok", "pull 0 from-cpp", "stream 0 1", "anon 16"]
