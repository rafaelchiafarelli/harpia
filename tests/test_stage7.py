"""Stage 7 test -- protoc turns the emitted .proto into compilable C++.

Runs the front-end (via run_pipeline.py) to produce the proto tree, then drives
ProtoCompiler over it and asserts:

  - protoc succeeds and emits one .pb.h/.pb.cc per input .proto
  - every generated .pb.cc actually compiles with g++ (the real proof that the
    emitted protos are well-formed C++-generating protos)

The whole module is skipped when protoc is unavailable, so a host without the
toolchain (run pytest outside Docker) stays green. Inside the harpia Docker
image both protoc and g++ are present. See docker/run.sh:

    docker/run.sh pytest tests/
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

pytestmark = pytest.mark.skipif(
    shutil.which("protoc") is None,
    reason="protoc not on PATH (run inside the harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    """Run the front-end, then Stage 7, returning (build_dir, error)."""
    out = tmp_path_factory.mktemp("harpia_stage7")
    result = subprocess.run(
        [sys.executable, RUNNER, str(out)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    err = ProtoCompiler(dest=build).Process()
    return build, err


def test_protoc_succeeds(compiled):
    build, err = compiled
    assert err is None, "Stage 7 returned an error: {}".format(err)


def test_one_pb_per_proto(compiled):
    build, _ = compiled
    protos = glob.glob(os.path.join(build, "proto", "protofiles", "*.proto"))
    gen = os.path.join(build, "generated", "cpp", "protofiles")
    headers = glob.glob(os.path.join(gen, "*.pb.h"))
    sources = glob.glob(os.path.join(gen, "*.pb.cc"))
    assert len(protos) > 0
    assert len(headers) == len(protos)
    assert len(sources) == len(protos)


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not on PATH")
def test_generated_cpp_compiles(compiled):
    build, _ = compiled
    cpp_root = os.path.join(build, "generated", "cpp")
    sources = sorted(glob.glob(os.path.join(cpp_root, "protofiles", "*.pb.cc")))
    assert sources, "no .pb.cc generated"
    for src in sources:
        r = subprocess.run(
            ["g++", "-std=c++17", "-I", cpp_root, "-c", src, "-o", os.devnull],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "{} failed to compile:\n{}".format(
            os.path.basename(src), r.stderr)
