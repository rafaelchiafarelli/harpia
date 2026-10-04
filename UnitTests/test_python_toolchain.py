"""The Python-target toolchain in the harpia-build image (python-target /
py-foundation task 1).

Asserts the pins recorded in the Dockerfile header: the apt runtimes match
protoc 3.21.12's gencode, the pinned pip tools are present, libzmq has
CURVE, cyclonedds is the same 0.10.5 as the C++ DDS stack, and a trivial
.proto compiles to importable _pb2 / _pb2.pyi / _pb2_grpc modules with the
system protoc + grpc_python_plugin (never grpc_tools' bundled protoc).

Skipped outside the image: the gate is the presence of grpc_python_plugin
plus the cyclonedds Python package.
"""
import importlib
import importlib.metadata
import os
import shutil
import subprocess
import sys

import pytest

GRPC_PY_PLUGIN = shutil.which("grpc_python_plugin")


def _has_module(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    GRPC_PY_PLUGIN is None or shutil.which("protoc") is None
    or not _has_module("cyclonedds"),
    reason="Python-target toolchain not installed (runs in the harpia-build image)")

# module -> expected version prefix (Dockerfile header pins)
EXPECTED = {
    "protobuf": "4.21.12",  # protoc 3.21.12 == python protobuf 4.21.12 (same release)
    "grpcio": "1.51.1",
    "pyzmq": "24.0.1",
    "psycopg": "3.1.17",
    "mypy": "1.9.0",
    "sphinx": "7.2.6",
    "ruff": "0.6.9",
    "types-protobuf": "4.21.0.7",
    "cyclonedds": "0.10.5",
}


@pytest.mark.parametrize("dist,version", sorted(EXPECTED.items()))
def test_pinned_versions(dist, version):
    assert importlib.metadata.version(dist).startswith(version)


@pytest.mark.parametrize("module", ["google.protobuf", "grpc", "zmq", "psycopg",
                                    "mypy", "sphinx", "cyclonedds.domain"])
def test_modules_import(module):
    importlib.import_module(module)


def test_zmq_has_curve():
    import zmq
    assert zmq.has("curve")


@pytest.mark.parametrize("cmd", [["ruff", "--version"], ["mypy", "--version"],
                                 ["sphinx-build", "--version"],
                                 ["protoc-gen-mypy", "--version"]])
def test_tools_run(cmd):
    if cmd[0] == "protoc-gen-mypy":
        # a protoc plugin: no --version flag, presence on PATH is the check
        assert shutil.which(cmd[0])
        return
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_protoc_python_codegen_imports(tmp_path):
    proto_dir = tmp_path / "protofiles"
    proto_dir.mkdir()
    (proto_dir / "probe.proto").write_text(
        'syntax = "proto3";\npackage probe;\n'
        "message Ping { int32 a = 1; string s = 2; }\n"
        "service Pinger { rpc Echo(Ping) returns (Ping); }\n")
    r = subprocess.run(
        ["protoc", "-I", str(tmp_path), "--python_out", str(tmp_path),
         "--pyi_out", str(tmp_path), "--grpc_python_out", str(tmp_path),
         "--plugin=protoc-gen-grpc_python=" + GRPC_PY_PLUGIN,
         "protofiles/probe.proto"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    for name in ("probe_pb2.py", "probe_pb2.pyi", "probe_pb2_grpc.py"):
        assert (proto_dir / name).is_file(), name

    probe = (
        "from protofiles import probe_pb2, probe_pb2_grpc\n"
        "m = probe_pb2.Ping(a=3, s='x')\n"
        "b = m.SerializeToString()\n"
        "assert probe_pb2.Ping.FromString(b) == m\n"
        "assert hasattr(probe_pb2_grpc, 'PingerServicer')\n"
        "print(b.hex())\n")
    r = subprocess.run([sys.executable, "-c", probe], cwd=str(tmp_path),
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PYTHONPATH=str(tmp_path)))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "08031201" + "78"
