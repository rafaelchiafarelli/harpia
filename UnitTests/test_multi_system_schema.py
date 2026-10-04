"""multi-system-reference / reference-system task 2 -- the reference schema
(`HarpiaTest/app_example/multi_system/harpia/`) generates for both targets.

One `.harpia` + one hardened `project.harpia.yaml` (topology cloud_connected)
for three programs: `station` (C++, DB owner), `edge` (C++, no DB), `handheld`
(Java). Generation is the test's own (nothing generated is committed):
  * C++: gRPC services + server bring-up for the two table messages
    (`reading`, `field_note`), hardened (mTLS + RBAC + sessions); a ZMQ
    publisher/subscriber with the ZAP allowlist hook for `live_sample`;
    migrations for both tables; no DB / gRPC surface for `live_sample`.
  * Java: message classes, gRPC stubs (`*_service.proto` copied for the
    Gradle build), the hardened client runtime, `live_sample_zmq` factories.
  * `clients.txt`: the identities and roles the programs use -- edge and
    handheld are `main`, `guest` exists only to prove a denial, station has
    no client identity.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._multi_system_helpers import SCHEMA_DIR, generate, schema_hash  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    out = generate(tmp_path_factory.mktemp("ms_gen"), lang="java")
    return out, schema_hash(out)


def test_schema_files_and_profile():
    harpia = _read(os.path.join(SCHEMA_DIR, "multi_system.harpia"))
    for msg in ("message reading", "message field_note", "message live_sample"):
        assert msg in harpia
    profile = _read(os.path.join(SCHEMA_DIR, "project.harpia.yaml"))
    assert "topology: cloud_connected" in profile
    rows = [ln.split() for ln in _read(os.path.join(SCHEMA_DIR, "clients.txt")).splitlines()
            if ln.strip() and not ln.startswith("#")]
    assert dict(rows) == {"edge": "main", "handheld": "main", "guest": "guest"}


def test_cpp_server_surface_is_hardened(gen):
    out, h = gen
    cpp = os.path.join(out, "generated", "cpp")
    bringup = _read(os.path.join(cpp, "grpc", "grpc_server_bringup.h"))
    assert "kHardeningRequired = true" in bringup
    for name in ("reading", "field_note"):
        svc = _read(os.path.join(cpp, "grpc", "{}_{}_grpc.h".format(name, h)))
        assert "rbac_check(" in svc and "harpia-issue-session" in svc
        assert "::soci::connection_pool& pool" in svc
        assert os.path.isfile(os.path.join(cpp, "migrate", "{}_{}_migrate.h".format(name, h)))
        assert os.path.isfile(os.path.join(cpp, "protofiles",
                                           "{}_{}_service.grpc.pb.h".format(name, h)))
    # live_sample is table-less: no DAO, no gRPC service
    assert not os.path.exists(os.path.join(cpp, "grpc", "live_sample_{}_grpc.h".format(h)))
    assert not os.path.exists(os.path.join(cpp, "db", "live_sample_{}_crudl.h".format(h)))


def test_cpp_live_sample_pubsub_with_zap(gen):
    out, h = gen
    zmq = _read(os.path.join(out, "generated", "cpp", "zmq", "live_sample_{}_zmq.h".format(h)))
    assert "class live_sample_publisher" in zmq and "class live_sample_subscriber" in zmq
    assert "::harpia::zap::ensure_running(ctx);" in zmq
    assert os.path.isfile(os.path.join(out, "generated", "cpp", "zap", "harpia_zap.h"))


def test_java_client_surface(gen):
    out, _ = gen
    java = os.path.join(out, "java", "src", "main")
    protos = os.listdir(os.path.join(java, "proto", "protofiles"))
    assert any(p.startswith("reading_") and p.endswith("_service.proto") for p in protos)
    assert any(p.startswith("field_note_") and p.endswith("_service.proto") for p in protos)
    zmq = _read(os.path.join(java, "java", "com", "harpia", "generated", "zmq", "live_sample_zmq.java"))
    assert "newPublisher" in zmq and "newSubscriber" in zmq
    for runtime in ("grpc/HarpiaGrpcTls.java", "grpc/HarpiaSession.java", "zmq/HarpiaZmq.java"):
        assert os.path.isfile(os.path.join(java, "java", "com", "harpia", "runtime", runtime)), runtime
