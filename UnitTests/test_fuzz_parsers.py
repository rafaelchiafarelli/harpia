"""static-fuzz-ci epic / tasks 2-4 -- hand-rolled fuzz harness for the
JSON / XML / SOAP parser entry points.

Compiles `UnitTests/fuzz/harpia_fuzz_main.cpp` once per target with
`g++ -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all
-DHARPIA_FUZZ_TARGET=<t>` against the generated C++ tree
(`run_pipeline.py`), then runs it against the checked-in seed corpus
(`UnitTests/fuzz/corpus/<t>/`). A parser rejecting an input (`false`) is
fine; only an AddressSanitizer / UBSan trip -- which aborts the process --
fails the job. The run is bounded (default 5000 mutations/target, env
`HARPIA_FUZZ_ITERS`) and deterministic (fixed PRNG seed, env
`HARPIA_FUZZ_SEED`), so it costs seconds and any crash reproduces.

`@pytest.mark.fuzz` (registered in `pytest.ini`): runs by default in the
full Docker suite; `pytest -m "not fuzz"` skips it. `skipif` when `g++` or
`pkg-config` is absent (same discipline as `test_stage10_serialize.py`).

Targets: task 2 ships `json`; task 3 adds `xml`; task 4 adds `soap`. Each
uncovered target's `#error` branch in the driver is why `TARGETS` is
grown one entry at a time rather than discovered from the corpus tree.

A longer local campaign is encouraged but not a CI gate -- see
`UnitTests/fuzz/README.md` (`HARPIA_FUZZ_ITERS=5000000 ...`).
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
FUZZ_DIR = os.path.join(HERE, "fuzz")
DRIVER = os.path.join(FUZZ_DIR, "harpia_fuzz_main.cpp")
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")

ITERS = os.environ.get("HARPIA_FUZZ_ITERS", "5000")

TARGETS = ["json", "xml", "soap"]

pytestmark = [
    pytest.mark.fuzz,
    pytest.mark.skipif(
        any(shutil.which(t) is None for t in ("g++", "pkg-config")),
        reason="needs g++ + pkg-config(protobuf) (harpia Docker image)"),
]


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    assert out.returncode == 0, "pkg-config protobuf failed:\n" + out.stderr
    return out.stdout.split()


@pytest.fixture(scope="module")
def cpp_root(tmp_path_factory):
    """The assembled generated C++ tree -- the driver only needs the runtime
    headers in it (serialize/xml/yaml), not any .pb.cc."""
    out = tmp_path_factory.mktemp("harpia_fuzz")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    root = os.path.join(str(out), "build", "generated", "cpp")
    assert os.path.isdir(root), "run_pipeline.py produced no generated/cpp tree"
    return root


@pytest.mark.parametrize("target", TARGETS)
def test_fuzz_parser_no_sanitizer_trip(target, cpp_root, tmp_path):
    corpus = os.path.join(FUZZ_DIR, "corpus", target)
    assert os.path.isdir(corpus) and os.listdir(corpus), \
        "no seed corpus for target " + target

    binary = os.path.join(str(tmp_path), "fuzz_" + target)
    compile_cmd = [
        "g++", "-std=c++17", "-O1", "-g",
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        "-DHARPIA_FUZZ_TARGET=" + target,
        "-I", cpp_root, "-I", TINYXML2,
        *_pkgconfig("--cflags"),
        DRIVER, os.path.join(TINYXML2, "tinyxml2.cpp"),
        "-o", binary,
        *_pkgconfig("--libs"),
    ]
    c = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, \
        "fuzz driver ({}) failed to compile:\n{}".format(target, c.stderr)

    env = {**os.environ,
           "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=0:exitcode=99",
           "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1"}
    run = subprocess.run([binary, target, corpus, ITERS],
                         capture_output=True, text=True, timeout=300, env=env)
    assert run.returncode == 0, (
        "fuzz run for the {} target tripped a sanitizer / crashed (exit {}).\n"
        "stdout:\n{}\nstderr:\n{}".format(
            target, run.returncode, run.stdout, run.stderr))
    assert run.stdout.startswith("ok:"), run.stdout + "\n" + run.stderr
