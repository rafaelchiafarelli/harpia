"""Stage 9 test -- the JSON adapters are real, compilable C++.

After the front-end + Stage 7, this:
  - compiles every generated adapter header against its real protobuf message
    header (proves the wrapper is well-formed against actual generated code), and
  - builds and RUNS a JSON round-trip: set fields -> to_json -> from_json and
    assert the message survives, plus is_valid_json accepts good JSON and
    rejects garbage.

Skipped when protoc/g++/pkg-config are unavailable, so the host suite stays
green; inside the harpia Docker image it exercises fully:

    docker/run.sh pytest tests/test_stage9.py
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

pytestmark = pytest.mark.skipif(
    shutil.which("protoc") is None or shutil.which("g++") is None,
    reason="needs protoc + g++ (run inside the harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Front-end + Stage 7, returning paths into the build tree."""
    out = tmp_path_factory.mktemp("harpia_stage9")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "build": build,
        "cpp_root": cpp_root,
        "json_dir": os.path.join(cpp_root, "json"),
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tmp": str(out),
    }


def _class_and_hash(adapter_filename):
    """`prince_<hash>_json.h` -> ("prince", "<hash>")."""
    m = re.match(r"^(.*)_([0-9a-f]+)_json\.h$", adapter_filename)
    assert m, "unexpected adapter name {}".format(adapter_filename)
    return m.group(1), m.group(2)


def test_every_adapter_compiles(built):
    adapters = sorted(glob.glob(os.path.join(built["json_dir"], "*_json.h")))
    assert adapters, "no JSON adapters generated"
    cflags = _pkgconfig("--cflags")
    for adapter in adapters:
        cls, _ = _class_and_hash(os.path.basename(adapter))
        tu = os.path.join(built["tmp"], "use_{}.cc".format(cls))
        with open(tu, "w") as f:
            f.write(
                '#include "json/{}"\n'
                "#include <string>\n"
                "void use() {{\n"
                "    ::{cls} m; std::string s;\n"
                "    (void)harpia::json::to_json(m, &s);\n"
                "    (void)harpia::json::from_json(s, &m);\n"
                "    (void)harpia::json::is_valid_json(s);\n"
                "}}\n".format(os.path.basename(adapter), cls=cls)
            )
        r = subprocess.run(
            ["g++", "-std=c++17", "-I", built["cpp_root"], *cflags,
             "-c", tu, "-o", os.devnull],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "{} adapter failed to compile:\n{}".format(
            cls, r.stderr)


def test_json_roundtrip_runs(built):
    """Build + run a real round-trip for vip_users (clean string fields)."""
    adapters = glob.glob(os.path.join(built["json_dir"], "vip_users_*_json.h"))
    assert adapters, "vip_users adapter missing"
    adapter = os.path.basename(adapters[0])
    _, h = _class_and_hash(adapter)

    prog = os.path.join(built["tmp"], "roundtrip.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "json/{adapter}"\n'
            "#include <string>\n"
            "int main() {{\n"
            "    ::vip_users a;\n"
            '    a.set_name("alice");\n'
            '    a.set_family("smith");\n'
            "    std::string js;\n"
            "    if (!harpia::json::to_json(a, &js)) return 1;\n"
            '    if (js.find("alice") == std::string::npos) return 2;\n'
            "    ::vip_users b;\n"
            "    if (!harpia::json::from_json(js, &b)) return 3;\n"
            '    if (b.name() != "alice" || b.family() != "smith") return 4;\n'
            "    if (!harpia::json::is_valid_json(js)) return 5;\n"
            '    if (harpia::json::is_valid_json("this is not json")) return 6;\n'
            "    return 0;\n"
            "}}\n".format(adapter=adapter)
        )

    pb_cc = os.path.join(built["proto_dir"], "vip_users_{}.pb.cc".format(h))
    binary = os.path.join(built["tmp"], "roundtrip")
    compile_cmd = ["g++", "-std=c++17", "-I", built["cpp_root"],
                   *_pkgconfig("--cflags"), prog, pb_cc, "-o", binary,
                   *_pkgconfig("--libs")]
    c = subprocess.run(compile_cmd, capture_output=True, text=True)
    assert c.returncode == 0, "round-trip program failed to build:\n" + c.stderr

    run = subprocess.run([binary], capture_output=True, text=True)
    assert run.returncode == 0, "round-trip failed at check #{}".format(
        run.returncode)
