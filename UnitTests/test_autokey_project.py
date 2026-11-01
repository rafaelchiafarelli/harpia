"""dao-key-access / db-assigned-key: a whole generated project on an `autokey`
schema, not just its DAO -- every generated caller of create() has to work.

- C++: the generated ctest suite passes, and the gRPC service + dbio headers
  (const create() callers) compile;
- Python: the emitted pytest suite passes;
- a composed field pointing at an autokey message is AUTOKEY_FK_TARGET.
"""
import glob
import hashlib
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

SCHEMA = "autokey message ticket {\n    required string title;\n    int points;\n} ticket_table;\n"
TOOLCHAIN = all(shutil.which(t) for t in ("cmake", "protoc", "g++", "pkg-config"))


def _generate(tmp_path, schema=SCHEMA, lang=None):
    (tmp_path / "Include").mkdir(exist_ok=True)
    (tmp_path / "Include" / "mod.harpia").write_text(schema)
    root = tmp_path / "root.harpia"
    root.write_text('import "mod.harpia";\n')
    out = tmp_path / "gen"
    cfg = tmp_path / "low_risk.harpia.yaml"
    cfg.write_text("risk_class: class_a\ntopology: standalone\n")
    env = dict(os.environ, HARPIA_OUTPUT_DIR=str(out), HARPIA_INPUT_FILE=str(root),
               HARPIA_INCLUDE_FOLDER=str(tmp_path / "Include"),
               HARPIA_COMPLIANCE_CONFIG=str(cfg))
    env.pop("HARPIA_GEN_LANG", None)
    if lang:
        env["HARPIA_GEN_LANG"] = lang
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    return r, out, hashlib.md5(root.read_bytes()).hexdigest()


@pytest.mark.skipif(not TOOLCHAIN, reason="needs cmake + protoc + g++ (harpia Docker image)")
def test_generated_cpp_suite_and_const_callers(tmp_path):
    r, out, h = _generate(tmp_path)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    build = str(tmp_path / "build")
    cfg = subprocess.run(["cmake", "-S", str(out), "-B", build, "-DHARPIA_BUILD_TESTS=ON"],
                         capture_output=True, text=True, timeout=300)
    assert cfg.returncode == 0, cfg.stdout + cfg.stderr
    targets = [os.path.basename(c).split("_" + h)[0] + "_test"
               for c in glob.glob(str(out / "tests" / "*_test.cpp"))]
    assert "ticket_test" in targets
    b = subprocess.run(["cmake", "--build", build, "-j", "4", "--target", *targets],
                       capture_output=True, text=True, timeout=900)
    assert b.returncode == 0, b.stdout[-4000:] + b.stderr[-4000:]
    t = subprocess.run(["ctest", "--output-on-failure"], cwd=build,
                       capture_output=True, text=True, timeout=180)
    assert t.returncode == 0, t.stdout + t.stderr

    # the gRPC service and dbio call create() on const / local messages
    cpp_root = out / "generated" / "cpp"
    tu = tmp_path / "callers.cpp"
    tu.write_text('#include "grpc/ticket_{h}_grpc.h"\n#include "dbio/ticket_{h}_dbio.h"\n'
                  "int main() {{ return 0; }}\n".format(h=h))
    flags = subprocess.run(["pkg-config", "--cflags", "protobuf"],
                           capture_output=True, text=True).stdout.split()
    c = subprocess.run(["g++", "-std=c++17", "-fsyntax-only", "-I", str(cpp_root),
                        "-I", os.path.join(REPO_ROOT, "third_party", "tinyxml2"),
                        *flags, str(tu)],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr[-4000:]


@pytest.mark.skipif(not TOOLCHAIN, reason="needs the Python target toolchain (harpia Docker image)")
def test_generated_python_suite(tmp_path):
    r, out, _ = _generate(tmp_path, lang="python")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                       cwd=str(out / "python"), capture_output=True, text=True, timeout=600)
    assert t.returncode == 0, t.stdout[-4000:] + t.stderr[-2000:]


def test_composed_field_to_autokey_is_refused(tmp_path):
    r, _, _ = _generate(tmp_path, SCHEMA + "message board {\n    ticket top;\n} board_table;\n")
    assert r.returncode != 0
    assert "AUTOKEY_FK_TARGET" in r.stdout and "board.top -> ticket" in r.stdout, r.stdout[-2000:]
