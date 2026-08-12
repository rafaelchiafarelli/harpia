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
import ssl
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


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs the openssl CLI")
def test_consumer_builds_and_runs_tls(generated, tmp_path):
    """Same contract as the plain test, but with -DUSE_TLS=ON: proves TLS is not
    just a flag that compiles -- the running server does a real TLS handshake."""
    build = str(tmp_path / "consumer_build_tls")
    cfg = subprocess.run(
        ["cmake", "-S", CONSUMER, "-B", build,
         "-DHARPIA_GEN={}".format(generated), "-DUSE_TLS=ON"],
        capture_output=True, text=True, timeout=180)
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stdout + cfg.stderr

    b = subprocess.run(["cmake", "--build", build, "-j", "4"],
                       capture_output=True, text=True, timeout=300)
    assert b.returncode == 0, "consumer build failed:\n" + b.stdout + b.stderr

    env = dict(os.environ, HARPIA_DEMO_HOLD_MS="1500")
    proc = subprocess.Popen(
        [os.path.join(build, "consumer")], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = []
    try:
        port = None
        for line in proc.stdout:
            lines.append(line)
            if "REST server started on https://127.0.0.1:" in line:
                port = int(line.strip().rsplit(":", 1)[-1].split("/", 1)[0])
                break
        assert port is not None, "server never printed its https:// URL:\n" + "".join(lines)

        # A real TLS handshake against the still-running server (self-signed, so
        # we don't verify the chain -- the point is proving it's TLS, not who
        # signed it). The HARPIA_DEMO_HOLD_MS env var above keeps the server up
        # long enough for this to land before the process stops it.
        pem = ssl.get_server_certificate(("127.0.0.1", port))
        assert "BEGIN CERTIFICATE" in pem

        rest, _ = proc.communicate(timeout=10)
        lines.append(rest)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    out = "".join(lines)
    assert proc.returncode == 0, "consumer run failed:\n" + out
    assert "rows in the table: 2" in out, out
    assert "as JSON:" in out, out
    assert out.strip().endswith("OK"), out
