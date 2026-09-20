"""transport-multipeer-coverage / zmq-multipeer task 6 -- the worked example
under HarpiaTest/app_example/fanout/, downstream-consumption contract test.

Mirrors test_consumer_example.py's shape: build the example against a
freshly generated project (`cmake -DHARPIA_GEN=<gen>` for the C++ binaries,
`gradle build -PharpiaGenDir=<gen_java>` for the Java twins), then actually
run a small mixed set -- 1 C++ publisher + 2 C++ subscribers + 1 Java
subscriber; 1 C++ pusher + 1 C++ worker + 1 Java worker -- asserting it
behaves exactly as tasks 1/2/4/5 already proved structurally, so the example
never silently drifts from what's actually tested.

Needs both the C++ toolchain (cmake+protoc+g+++pkg-config+libzmq+cppzmq) and
gradle+JDK.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
FANOUT = os.path.join(REPO_ROOT, "HarpiaTest", "app_example", "fanout")
FANOUT_JAVA = os.path.join(FANOUT, "java")


def _have_libzmq():
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


_HAS_CPP_TOOLCHAIN = (
    all(shutil.which(t) is not None for t in ("cmake", "protoc", "g++", "pkg-config"))
    and _have_libzmq()
    and os.path.exists("/usr/include/zmq.hpp")
)
_HAS_JAVA_TOOLCHAIN = shutil.which("gradle") is not None and shutil.which("java") is not None

pytestmark = pytest.mark.skipif(
    not _HAS_CPP_TOOLCHAIN or not _HAS_JAVA_TOOLCHAIN,
    reason="needs cmake+protoc+g+++pkg-config+libzmq+cppzmq AND gradle+JDK (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate, build_and_classpath  # noqa: E402


@pytest.fixture(scope="module")
def cpp_binaries(tmp_path_factory):
    gen = str(tmp_path_factory.mktemp("harpia_fanout_gen_cpp"))
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT,
                       env=dict(os.environ, HARPIA_OUTPUT_DIR=gen,
                                HARPIA_INPUT_FILE="./HarpiaTest/test.harpia",
                                HARPIA_INCLUDE_FOLDER="./HarpiaTest/Include"),
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr

    build = str(tmp_path_factory.mktemp("harpia_fanout_build"))
    cfg = subprocess.run(["cmake", "-S", FANOUT, "-B", build,
                          "-DHARPIA_GEN={}".format(gen)],
                        capture_output=True, text=True, timeout=180)
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stdout + cfg.stderr
    b = subprocess.run(["cmake", "--build", build, "-j", "4"],
                       capture_output=True, text=True, timeout=300)
    assert b.returncode == 0, "fanout example build failed:\n" + b.stdout + b.stderr

    return {name: os.path.join(build, name)
           for name in ("publisher", "subscriber", "pusher", "worker")}


@pytest.fixture(scope="module")
def java_classpath(tmp_path_factory):
    gen_java = generate(tmp_path_factory.mktemp("harpia_fanout_gen_java"), lang="java")
    java_gen_root = os.path.join(gen_java, "java")
    # build the generated project itself first -- its jar is what the fanout
    # consumer's fileTree(dir: ".../java/build/libs") depends on.
    build_and_classpath(java_gen_root, {})

    build = subprocess.run(
        ["gradle", "build", "-PharpiaGenDir={}".format(gen_java)],
        cwd=FANOUT_JAVA, capture_output=True, text=True, timeout=300)
    assert build.returncode == 0, \
        "fanout java example build failed:\n" + build.stdout + build.stderr

    jars = glob.glob(os.path.join(FANOUT_JAVA, "build", "libs", "*.jar"))
    assert jars, "gradle build produced no jar for the fanout java example"

    cp = subprocess.run(
        ["gradle", "-q", "--console=plain", "classpath",
         "-PharpiaGenDir={}".format(gen_java)],
        cwd=FANOUT_JAVA, capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, "classpath task failed:\n" + cp.stdout + cp.stderr
    line = next((l for l in cp.stdout.splitlines()
                if l.startswith("FANOUT_CLASSPATH=")), None)
    assert line, "no FANOUT_CLASSPATH= line in:\n" + cp.stdout
    dep_classpath = line[len("FANOUT_CLASSPATH="):]

    return os.pathsep.join(jars) + os.pathsep + dep_classpath


def _kill_and_read(proc, grace=1.0):
    time.sleep(grace)
    if proc.poll() is None:
        proc.kill()
    out, _ = proc.communicate(timeout=10)
    return out


def _wait_for_line(proc, substring, max_lines=50):
    """Block until `proc` prints a line containing `substring`, tolerating
    noise before it (e.g. JeroMQ/SLF4J's static-init warning on first touch,
    or Gradle daemon chatter). Used as an event-driven "this peer is up and
    connected" signal instead of a blind sleep -- a fixed sleep across 3
    concurrently-started processes (one a JVM) proved flaky under load: a
    subscriber whose *process* was simply slow to start, not the usual
    ZMQ wire-propagation "slow joiner", missed the very first tick even
    after a generous 1s settle."""
    lines = []
    for _ in range(max_lines):
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if substring in line:
            return
    proc.kill()
    proc.communicate(timeout=10)
    raise AssertionError(
        "{} never printed a line containing {!r} within {} lines:\n{}".format(
            proc.args, substring, max_lines, "".join(lines)))


def test_pubsub_fanout_example_mixed_languages(cpp_binaries, java_classpath):
    endpoint = "tcp://127.0.0.1:15561"
    count = 8

    subs = [
        subprocess.Popen([cpp_binaries["subscriber"], endpoint],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
        subprocess.Popen([cpp_binaries["subscriber"], endpoint],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
        subprocess.Popen(["java", "-cp", java_classpath, "com.harpia.fanout.Subscriber",
                          endpoint],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True),
    ]
    try:
        for s in subs:
            _wait_for_line(s, "connected to")
        time.sleep(0.5)  # wire-level subscription-propagation settle (the usual slow-joiner window)

        pub = subprocess.Popen([cpp_binaries["publisher"], endpoint, str(count)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        pub_out, _ = pub.communicate(timeout=20)
        assert pub.returncode == 0, "publisher failed:\n" + pub_out

        for i, s in enumerate(subs):
            out = _kill_and_read(s)
            received = [int(m) for m in re.findall(r"received sequence=(\d+)", out)]
            assert received == list(range(1, count + 1)), \
                "subscriber {} got {} (raw output:\n{})".format(i, received, out)
    finally:
        for s in subs:
            if s.poll() is None:
                s.kill()
                s.communicate()


def test_pushpull_loadbalance_example_mixed_languages(cpp_binaries, java_classpath):
    cpp_endpoint = "tcp://127.0.0.1:15571"
    java_endpoint = "tcp://127.0.0.1:15572"
    count = 12

    cpp_worker = subprocess.Popen([cpp_binaries["worker"], cpp_endpoint],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    java_worker = subprocess.Popen(
        ["java", "-cp", java_classpath, "com.harpia.fanout.Worker", java_endpoint],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    workers = [cpp_worker, java_worker]
    try:
        for w in workers:
            _wait_for_line(w, "bound to")

        pusher = subprocess.Popen(
            [cpp_binaries["pusher"], cpp_endpoint, java_endpoint, "--count", str(count)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        pusher_out, _ = pusher.communicate(timeout=20)
        assert pusher.returncode == 0, "pusher failed:\n" + pusher_out

        seen = set()
        per_worker_counts = []
        for i, w in enumerate(workers):
            out = _kill_and_read(w)
            seqs = [int(m) for m in re.findall(r"processed seq-(\d+)", out)]
            per_worker_counts.append(len(seqs))
            for s in seqs:
                assert s not in seen, "sequence {} delivered more than once".format(s)
                seen.add(s)

        assert seen == set(range(1, count + 1)), \
            "union mismatch: missing {}, unexpected {}".format(
                set(range(1, count + 1)) - seen, seen - set(range(1, count + 1)))
        for i, c in enumerate(per_worker_counts):
            assert c > 0, "worker {} (lang {}) got nothing".format(
                i, "java" if i == 1 else "cpp")
            assert c < count, "worker {} got everything -- work didn't distribute".format(i)
    finally:
        for w in workers:
            if w.poll() is None:
                w.kill()
                w.communicate()
