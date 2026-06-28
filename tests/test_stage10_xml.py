"""Stage 10 (XML) test -- the XML adapter is real, compilable C++.

After the front-end + Stage 7, this:
  - compiles every generated XML wrapper against the reflection runtime, and
  - builds and RUNS a write check: set fields -> to_xml and assert the values
    appear in the XML.

The read (from_xml) round-trip and XSD checks are added alongside those steps.

Skipped unless protoc + g++ + pkg-config(protobuf) are present, so the host
suite stays green; runs in the harpia Docker image.
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
TINYXML2 = os.path.join(REPO_ROOT, "third_party", "tinyxml2")

HASH = "734126ee6efdfbd64a1678bf49ee9683"

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "g++", "pkg-config")),
    reason="needs protoc + g++ + protobuf (harpia Docker image)",
)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_xml")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "cpp_root": cpp_root,
        "xml_dir": os.path.join(cpp_root, "xml"),
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tmp": str(out),
    }


def _name_of(wrapper):
    return os.path.basename(wrapper)[:-len("_{}_xml.h".format(HASH))]


def _wrappers(xml_dir):
    # the per-message wrappers, excluding the static runtime header
    return sorted(w for w in glob.glob(os.path.join(xml_dir, "*_xml.h"))
                  if os.path.basename(w) != "harpia_xml.h")


def test_every_xml_adapter_compiles(built):
    wrappers = _wrappers(built["xml_dir"])
    assert wrappers, "no XML adapters generated"
    cflags = _pkgconfig("--cflags")
    for wrapper in wrappers:
        name = _name_of(wrapper)
        tu = os.path.join(built["tmp"], "usexml_{}.cc".format(name))
        with open(tu, "w") as f:
            f.write(
                '#include "xml/{}"\n'.format(os.path.basename(wrapper)) +
                "void use() {{\n"
                "    ::{name} m;\n"
                "    (void)harpia::xml::to_xml(m);\n"
                "}}\n".format(name=name)
            )
        r = subprocess.run(
            ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", TINYXML2,
             *cflags, "-c", tu, "-o", os.devnull],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "{} XML adapter failed to compile:\n{}".format(
            name, r.stderr)


def test_to_xml_writes_fields(built):
    prog = os.path.join(built["tmp"], "xml_write.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "xml/users_{h}_xml.h"\n'
            "#include <iostream>\n"
            "int main() {{\n"
            "    ::users m;\n"
            '    m.set_name("neo");\n'
            '    m.set_address("matrix");\n'
            "    std::cout << harpia::xml::to_xml(m);\n"
            "    return 0;\n"
            "}}\n".format(h=HASH)
        )
    pb_cc = os.path.join(built["proto_dir"], "users_{}.pb.cc".format(HASH))
    binary = os.path.join(built["tmp"], "xml_write")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", TINYXML2,
         *_pkgconfig("--cflags"), prog, pb_cc, "-o", binary,
         *_pkgconfig("--libs")],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "xml write program failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0
    assert "<name>neo</name>" in run.stdout, run.stdout
    assert "<address>matrix</address>" in run.stdout, run.stdout
    assert run.stdout.startswith("<users>"), run.stdout


def test_xml_roundtrip_runs(built):
    """to_xml -> from_xml preserves the message (links vendored tinyxml2)."""
    prog = os.path.join(built["tmp"], "xml_roundtrip.cc")
    with open(prog, "w") as f:
        f.write(
            '#include "xml/users_{h}_xml.h"\n'
            "int main() {{\n"
            "    ::users a;\n"
            '    a.set_name("neo");\n'
            '    a.set_address("matrix");\n'
            "    a.set_id_{h}(42);\n"
            "    const std::string xml = harpia::xml::to_xml(a);\n"
            "    ::users b;\n"
            "    if (!harpia::xml::from_xml(xml, &b)) return 1;\n"
            '    if (b.name() != "neo" || b.address() != "matrix") return 2;\n'
            "    if (b.id_{h}() != 42) return 3;\n"
            "    if (a.SerializeAsString() != b.SerializeAsString()) return 4;\n"
            "    ::users c;\n"
            '    if (harpia::xml::from_xml("not xml at all", &c)) return 5;\n'
            "    return 0;\n"
            "}}\n".format(h=HASH)
        )
    pb_cc = os.path.join(built["proto_dir"], "users_{}.pb.cc".format(HASH))
    tinyxml = os.path.join(TINYXML2, "tinyxml2.cpp")
    binary = os.path.join(built["tmp"], "xml_roundtrip")
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", TINYXML2,
         *_pkgconfig("--cflags"), prog, pb_cc, tinyxml, "-o", binary,
         *_pkgconfig("--libs")],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "xml round-trip failed to build:\n" + c.stderr
    run = subprocess.run([binary], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, "round-trip failed at check #{}".format(
        run.returncode)
