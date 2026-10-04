"""Generation-time protobuf/gRPC codegen for the Python target (python-target
/ py-foundation task 2, ``PyAdapter``).

Structural (pure Python, always run): the proto copies under
``python/proto/harpia_generated/protofiles/`` have every import re-rooted
under ``harpia_generated/``, and a stale ``<name>_<hash>_pb2.py`` is pruned.

protoc + grpc_python_plugin gated: every compiled module imports as
``harpia_generated.protofiles.<x>_pb2`` (decision (b): no top-level
``protofiles`` package), ``_pb2_grpc`` exists exactly for the protos that
declare a service, and a message parsed from the same text format encodes
to the **same bytes** in Python and in the C++ target's generated class
(protoc + g++ + pkg-config protobuf).
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate  # noqa: E402
from PyAdapter.PyAdapter import rewrite_proto_imports  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

HAVE_PY_PROTOC = (shutil.which("protoc") is not None
                  and shutil.which("grpc_python_plugin") is not None)
HAVE_CPP = (HAVE_PY_PROTOC and shutil.which("g++") is not None
            and shutil.which("pkg-config") is not None)

# shipment_Message (service proto, package frameworkProtos) -> shipment ->
# repeated parcel: crosses three files' imports, strings, ints, repeats.
TEXT = ('msg {{ ID_{h}: 7 tag: "box-1" '
        'cargo {{ ID_{h}: 1 label: "a" weight: 3 }} '
        'cargo {{ ID_{h}: 2 label: "b\\303\\251" weight: -4 ORIGINATOR: "o" }} '
        'ORIGINATOR: "edge" }}').format(h=HASH)


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    return generate(tmp_path_factory.mktemp("harpia_py_codegen"), lang="python")


def test_rewrite_proto_imports():
    src = ('import "protofiles/a.proto";\n  import public "protofiles/b.proto";\n'
           '// import "protofiles/c.proto" stays a comment\n')
    out = rewrite_proto_imports(src)
    assert 'import "harpia_generated/protofiles/a.proto";' in out
    assert 'import public "harpia_generated/protofiles/b.proto";' in out
    assert '// import "protofiles/c.proto"' in out


def test_proto_copies_are_rerooted(gen):
    pdir = os.path.join(gen, "python", "proto", "harpia_generated", "protofiles")
    protos = sorted(os.listdir(pdir))
    src = sorted(os.listdir(os.path.join(gen, "proto", "protofiles")))
    assert protos == src
    assert {"errorCode.proto", "heartBeat.proto",
            "capabilities_service.proto"} <= set(protos)
    for name in protos:
        text = open(os.path.join(pdir, name)).read()
        assert 'import "protofiles/' not in text, name
    svc = open(os.path.join(pdir, "users_{}_service.proto".format(HASH))).read()
    assert 'import "harpia_generated/protofiles/errorCode.proto";' in svc


def test_stale_pb2_is_pruned(tmp_path):
    out = generate(tmp_path, lang="python")
    pkg = os.path.join(out, "python", "harpia_generated", "protofiles")
    stale = os.path.join(pkg, "renamed_away_{}_pb2.py".format(HASH))
    with open(stale, "w") as f:
        f.write("# stale\n")
    generate(tmp_path, lang="python")
    assert not os.path.exists(stale)


@pytest.mark.skipif(not HAVE_PY_PROTOC, reason="needs protoc + grpc_python_plugin")
def test_every_module_imports_under_harpia_generated(gen):
    pyroot = os.path.join(gen, "python")
    pkg = os.path.join(pyroot, "harpia_generated", "protofiles")
    protos = glob.glob(os.path.join(pyroot, "proto", "harpia_generated",
                                    "protofiles", "*.proto"))
    stems = sorted(os.path.splitext(os.path.basename(p))[0] for p in protos)
    for stem in stems:
        assert os.path.isfile(os.path.join(pkg, stem + "_pb2.py")), stem
        assert os.path.isfile(os.path.join(pkg, stem + "_pb2.pyi")), stem
        has_service = "\nservice " in open(os.path.join(
            pyroot, "proto", "harpia_generated", "protofiles", stem + ".proto")).read()
        assert os.path.isfile(os.path.join(pkg, stem + "_pb2_grpc.py")) == has_service, stem
    assert not os.path.exists(os.path.join(pyroot, "protofiles"))

    script = (
        "import glob, importlib, os\n"
        "mods = sorted(os.path.basename(f)[:-3] for f in glob.glob("
        "'harpia_generated/protofiles/*_pb2*.py'))\n"
        "for m in mods: importlib.import_module('harpia_generated.protofiles.' + m)\n"
        "print(len(mods))\n")
    r = subprocess.run([sys.executable, "-c", script], cwd=pyroot,
                       capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, PYTHONPATH=pyroot))
    assert r.returncode == 0, r.stderr
    assert int(r.stdout.strip()) == len(glob.glob(os.path.join(pkg, "*_pb2*.py")))


def _python_bytes(pyroot):
    script = (
        "import sys\n"
        "from google.protobuf import text_format\n"
        "from harpia_generated.protofiles import shipment_{h}_service_pb2 as s\n"
        "m = text_format.Parse(sys.stdin.read(), s.shipment_Message())\n"
        "b = m.SerializeToString()\n"
        "assert s.shipment_Message.FromString(b) == m\n"
        "print(b.hex())\n").format(h=HASH)
    r = subprocess.run([sys.executable, "-c", script], cwd=pyroot, input=TEXT,
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PYTHONPATH=pyroot))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _cpp_bytes(gen, tmp_path):
    cpp_root = os.path.join(gen, "generated", "cpp")
    pdir = os.path.join(cpp_root, "protofiles")
    srcs = [os.path.join(pdir, n) for n in (
        "shipment_{}_service.pb.cc".format(HASH), "shipment_{}.pb.cc".format(HASH),
        "parcel_{}.pb.cc".format(HASH), "errorCode.pb.cc", "heartBeat.pb.cc")]
    probe = tmp_path / "probe.cpp"
    probe.write_text(
        "#include <google/protobuf/text_format.h>\n"
        "#include <iostream>\n#include <iterator>\n#include <cstdio>\n"
        '#include "protofiles/shipment_{h}_service.pb.h"\n'
        "int main() {{\n"
        "  std::string in((std::istreambuf_iterator<char>(std::cin)), {{}});\n"
        "  frameworkProtos::shipment_Message m;\n"
        "  if (!google::protobuf::TextFormat::ParseFromString(in, &m)) return 2;\n"
        "  std::string b; m.SerializeToString(&b);\n"
        "  for (unsigned char c : b) std::printf(\"%02x\", c);\n"
        "  std::printf(\"\\n\");\n}}\n".format(h=HASH))
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "probe"
    r = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(probe), *srcs,
                        "-o", str(exe), *flags, "-pthread"],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([str(exe)], input=TEXT, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.mark.skipif(not HAVE_CPP, reason="needs protoc + grpc_python_plugin + g++ + pkg-config")
def test_wire_bytes_match_cpp(gen, tmp_path):
    py = _python_bytes(os.path.join(gen, "python"))
    cpp = _cpp_bytes(gen, tmp_path)
    assert py and py == cpp
