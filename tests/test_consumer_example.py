"""Downstream-consumption contract test.

Builds and runs the worked example under ``examples/consumer/`` against a freshly
generated project, exactly as a downstream user would:

    run pipeline -> cmake -S examples/consumer -DHARPIA_GEN=<gen> -> build -> run

This keeps the black-box wiring contract (the generated headers, the vendored
Crow/asio/tinyxml2, and the SOCI/protobuf link surface documented in USAGE.md)
green as the generator evolves. Skipped when the C++ toolchain is absent; runs
fully in the harpia Docker image.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
CONSUMER = os.path.join(REPO_ROOT, "examples", "consumer")

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None
        for t in ("cmake", "protoc", "g++", "pkg-config")),
    reason="needs cmake + protoc + g++ + pkg-config (harpia Docker image)",
)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """Generate a full project (SQLite backend) via the real pipeline entrypoint."""
    out = str(tmp_path_factory.mktemp("harpia_consumer_gen"))
    env = dict(os.environ, HARPIA_OUTPUT_DIR=out,
               HARPIA_INPUT_FILE="./HarpiaTest/test.harpia",
               HARPIA_INCLUDE_FOLDER="./HarpiaTest/Include")
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    # the consumer's CMake needs these from the generated tree
    assert os.path.isdir(os.path.join(out, "generated", "cpp"))
    assert os.path.exists(os.path.join(out, "third_party", "crow", "crow.h"))
    assert os.path.exists(os.path.join(out, "third_party", "tinyxml2",
                                       "tinyxml2.cpp"))
    return out


def test_consumer_builds_and_runs(generated, tmp_path):
    build = str(tmp_path / "consumer_build")
    cfg = subprocess.run(
        ["cmake", "-S", CONSUMER, "-B", build,
         "-DHARPIA_GEN={}".format(generated)],
        capture_output=True, text=True, timeout=180)
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stdout + cfg.stderr

    b = subprocess.run(["cmake", "--build", build, "-j", "4"],
                       capture_output=True, text=True, timeout=300)
    assert b.returncode == 0, "consumer build failed:\n" + b.stdout + b.stderr

    run = subprocess.run([os.path.join(build, "consumer")],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, "consumer run failed:\n" + run.stdout + run.stderr
    # the example exercises DAO (list), JSON, and REST -- assert each surfaced
    assert "rows in the table: 2" in run.stdout, run.stdout
    assert "as JSON:" in run.stdout, run.stdout
    assert "REST server started" in run.stdout, run.stdout
    assert run.stdout.strip().endswith("OK"), run.stdout
