"""Stage 14 (generated unit tests) -- the emitted tests are real and pass.

Stage 14a generates, for every table-bearing message, a C++ unit-test program
(14.1 simple field access + 14.2 a CRUDL round-trip over in-memory SQLite) plus a
CTest CMakeLists, and wires an opt-in HARPIA_BUILD_TESTS option into the
generated project's top-level CMake. This verifies, end to end:

  - every generated *_test.cpp compiles against its real protobuf message + CRUDL
    DAO and RUNS green (compiled directly, like the other stage tests), and
  - the generated CTest wiring is well-formed and actually runs under cmake/ctest
    when configured with -DHARPIA_BUILD_TESTS=ON.

Skipped when the toolchain is absent so the host suite stays green; runs fully in
the harpia Docker image:

    docker/run.sh pytest tests/test_stage14.py
"""
import glob
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
SQLITE = os.path.join(REPO_ROOT, "third_party", "sqlite")

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None or shutil.which("cc") is None,
    reason="needs a C/C++ compiler for the vendored sqlite (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def _name_and_hash(test_filename):
    """`users_<hash>_test.cpp` -> ("users", "<hash>")."""
    m = re.match(r"^(.*)_([0-9a-f]+)_test\.cpp$", test_filename)
    assert m, "unexpected test name {}".format(test_filename)
    return m.group(1), m.group(2)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_stage14")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "build")


@pytest.fixture(scope="module")
def sqlite_obj(tmp_path_factory):
    """Compile the vendored sqlite3.c once (it is C; g++ would reject it)."""
    out = tmp_path_factory.mktemp("sqlite_obj_s14")
    obj = os.path.join(str(out), "sqlite3.o")
    c = subprocess.run(
        ["cc", "-c", "-I", SQLITE, os.path.join(SQLITE, "sqlite3.c"), "-o", obj],
        capture_output=True, text=True, timeout=300,
    )
    assert c.returncode == 0, "sqlite3.c failed to compile:\n" + c.stderr
    return obj


def test_unit_tests_generated(generated):
    tests_dir = os.path.join(generated, "tests")
    cpps = sorted(glob.glob(os.path.join(tests_dir, "*_test.cpp")))
    assert cpps, "no unit-test programs generated"
    assert os.path.exists(os.path.join(tests_dir, "CMakeLists.txt"))
    # SQLite must be vendored into the generated project so it stays self-contained.
    assert os.path.exists(os.path.join(generated, "third_party", "sqlite",
                                       "sqlite3.c"))


def test_ctest_wiring_is_wellformed(generated):
    tests_dir = os.path.join(generated, "tests")
    cmake = open(os.path.join(tests_dir, "CMakeLists.txt")).read()
    top = open(os.path.join(generated, "CMakeLists.txt")).read()

    assert "option(HARPIA_BUILD_TESTS" in top
    assert "enable_testing()" in top
    assert "add_subdirectory(tests)" in top

    for cpp in sorted(glob.glob(os.path.join(tests_dir, "*_test.cpp"))):
        cls, _ = _name_and_hash(os.path.basename(cpp))
        tgt = "{}_test".format(cls)
        assert "add_executable({} ".format(tgt) in cmake
        assert "add_test(NAME {} COMMAND {})".format(tgt, tgt) in cmake


@pytest.fixture(scope="module")
def messages_lib(generated, tmp_path_factory):
    """Compile every message .pb.cc (not the grpc stubs) once. A test message can
    embed another (a composed/FK field), so its .pb.cc references the dependent
    message's symbols -- linking all message objects mirrors the `protofiles`
    library the generated CMake builds."""
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=generated).Process() is None, "Stage 7 failed"
    cpp_root = os.path.join(generated, "generated", "cpp")
    proto_dir = os.path.join(cpp_root, "protofiles")
    out = tmp_path_factory.mktemp("pb_objs_s14")
    objs = []
    for cc in sorted(glob.glob(os.path.join(proto_dir, "*.pb.cc"))):
        if cc.endswith(".grpc.pb.cc"):
            continue
        obj = os.path.join(str(out), os.path.basename(cc) + ".o")
        c = subprocess.run(
            ["g++", "-std=c++17", "-I", cpp_root, *_pkgconfig("--cflags"),
             "-c", cc, "-o", obj], capture_output=True, text=True, timeout=300)
        assert c.returncode == 0, "{} failed to compile:\n{}".format(cc, c.stderr)
        objs.append(obj)
    return {"cpp_root": cpp_root, "objs": objs}


@pytest.mark.skipif(shutil.which("protoc") is None or shutil.which("pkg-config") is None,
                    reason="generated tests need protoc + protobuf for the message C++")
def test_every_generated_test_compiles_and_runs(generated, messages_lib,
                                                sqlite_obj, tmp_path):
    """Compile + run each *_test.cpp directly against its real message + DAO."""
    cpp_root = messages_lib["cpp_root"]
    cpps = sorted(glob.glob(os.path.join(generated, "tests", "*_test.cpp")))
    assert cpps, "no unit-test programs generated"
    for cpp in cpps:
        cls, _ = _name_and_hash(os.path.basename(cpp))
        binary = os.path.join(str(tmp_path), "{}_test".format(cls))
        c = subprocess.run(
            ["g++", "-std=c++17", "-I", cpp_root, "-I", SQLITE,
             *_pkgconfig("--cflags"), cpp, *messages_lib["objs"], sqlite_obj,
             "-o", binary, *_pkgconfig("--libs"), "-lpthread", "-ldl"],
            capture_output=True, text=True, timeout=180)
        assert c.returncode == 0, "{} test failed to build:\n{}".format(
            cls, c.stderr)
        run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, "{} unit test failed at check #{}".format(
            cls, run.returncode)


@pytest.mark.skipif(
    shutil.which("cmake") is None or shutil.which("protoc") is None,
    reason="CTest wiring proof needs cmake + protoc + gRPC (harpia Docker image)")
def test_ctest_target_builds_and_passes(generated, tmp_path):
    """Configure the generated project with -DHARPIA_BUILD_TESTS=ON, build the
    test targets (which pull in protofiles + the vendored sqlite), and run ctest."""
    build = str(tmp_path / "ctest_build")
    cfg = subprocess.run(
        ["cmake", "-S", generated, "-B", build, "-DHARPIA_BUILD_TESTS=ON"],
        capture_output=True, text=True, timeout=300)
    assert cfg.returncode == 0, "cmake configure failed:\n" + cfg.stdout + cfg.stderr

    targets = ["{}_test".format(_name_and_hash(os.path.basename(c))[0])
               for c in sorted(glob.glob(os.path.join(generated, "tests",
                                                      "*_test.cpp")))]
    assert targets, "no unit-test targets to build"
    b = subprocess.run(["cmake", "--build", build, "-j", "4", "--target", *targets],
                       capture_output=True, text=True, timeout=600)
    assert b.returncode == 0, "building test targets failed:\n" + b.stdout + b.stderr

    t = subprocess.run(["ctest", "--output-on-failure"], cwd=build,
                       capture_output=True, text=True, timeout=120)
    assert t.returncode == 0, "ctest failed:\n" + t.stdout + t.stderr
