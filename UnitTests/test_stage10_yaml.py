"""Stage 10 (YAML) test -- Track F / Session F.1.

The YAML adapter is real, compilable C++ (a reflection-based runtime + a thin
per-message wrapper, same shape as the JSON/XML adapters). After the front-end
+ Stage 7 this:
  - compiles every generated YAML wrapper against the reflection runtime,
  - builds and RUNS a write check (set fields -> to_yaml, assert the values
    and the mapping structure appear), and
  - round-trips a flat and a nested/repeated message through to_yaml/from_yaml.

F.1 is output-parity only: no `phi` redaction yet (F.3), JSON/XML/YAML are
still three separate code paths (F.2).

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

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

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
    out = tmp_path_factory.mktemp("harpia_yaml")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "cpp_root": cpp_root,
        "yaml_dir": os.path.join(cpp_root, "yaml"),
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tmp": str(out),
    }


def _wrappers(yaml_dir):
    return sorted(w for w in glob.glob(os.path.join(yaml_dir, "*_yaml.h"))
                  if os.path.basename(w) != "harpia_yaml.h")


def _name_of(wrapper):
    return os.path.basename(wrapper)[:-len("_{}_yaml.h".format(HASH))]


def _build_run(built, name, body, extra_pb=(), timeout=20):
    """Compile `body` (a full main()) against <name>'s wrapper + pb.cc, run it."""
    src = os.path.join(built["tmp"], "yaml_{}.cc".format(name))
    with open(src, "w") as f:
        f.write('#include "yaml/{}_{}_yaml.h"\n'.format(name, HASH) + body)
    pb_ccs = [os.path.join(built["proto_dir"], "{}_{}.pb.cc".format(n, HASH))
              for n in (name, *extra_pb)]
    binary = os.path.join(built["tmp"], "yaml_{}".format(name))
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", built["cpp_root"], *_pkgconfig("--cflags"),
         src, *pb_ccs, "-o", binary, *_pkgconfig("--libs")],
        capture_output=True, text=True, timeout=300,
    )
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    run = subprocess.run([binary], capture_output=True, text=True, timeout=timeout)
    return run


def test_every_yaml_adapter_compiles(built):
    wrappers = _wrappers(built["yaml_dir"])
    assert wrappers, "no YAML adapters generated"
    cflags = _pkgconfig("--cflags")
    for wrapper in wrappers:
        name = _name_of(wrapper)
        tu = os.path.join(built["tmp"], "useyaml_{}.cc".format(name))
        with open(tu, "w") as f:
            f.write(
                '#include "yaml/{}"\n'.format(os.path.basename(wrapper)) +
                "void use() {{\n"
                "    ::{name} m;\n"
                "    (void)harpia::yaml::to_yaml(m);\n"
                "    ::{name} b;\n"
                "    (void)harpia::yaml::from_yaml(harpia::yaml::to_yaml(m), &b);\n"
                "}}\n".format(name=name)
            )
        r = subprocess.run(
            ["g++", "-std=c++17", "-I", built["cpp_root"], *cflags,
             "-c", tu, "-o", os.devnull],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "{} YAML adapter failed to compile:\n{}".format(
            name, r.stderr)


def test_to_yaml_writes_fields_and_structure(built):
    run = _build_run(built, "users",
        "#include <iostream>\n"
        "int main() {{\n"
        "    ::users m;\n"
        '    m.set_name("neo");\n'
        '    m.set_address("matrix");\n'
        "    std::cout << harpia::yaml::to_yaml(m);\n"
        "}}\n")
    assert run.returncode == 0, run.stderr
    out = run.stdout
    # values present, strings quoted, scalars bare
    assert 'name: "neo"' in out, out
    assert 'address: "matrix"' in out, out
    # structure/keys always present -- even the ones left at their default
    assert "ID_{}: 0".format(HASH) in out, out
    assert "STATUS_{}:".format(HASH) in out, out
    # top-level block mapping: first line is `key: ...` at column 0, no wrapper
    assert not out.startswith(" "), out
    assert out.splitlines()[0].endswith(('"', "0")) and ":" in out.splitlines()[0]


def test_yaml_roundtrip_flat(built):
    run = _build_run(built, "users",
        "int main() {{\n"
        "    ::users a;\n"
        '    a.set_name("neo");\n'
        '    a.set_address("matrix");\n'
        "    a.set_id_{h}(42);\n"
        "    const std::string y = harpia::yaml::to_yaml(a);\n"
        "    ::users b;\n"
        "    if (!harpia::yaml::from_yaml(y, &b)) return 1;\n"
        '    if (b.name() != "neo" || b.address() != "matrix") return 2;\n'
        "    if (b.id_{h}() != 42) return 3;\n"
        "    if (a.SerializeAsString() != b.SerializeAsString()) return 4;\n"
        "    ::users c;\n"
        '    if (harpia::yaml::from_yaml("not yaml at all", &c)) return 5;\n'
        "    return 0;\n"
        "}}\n".format(h=HASH))
    assert run.returncode == 0, "flat round-trip failed at check #{}\n{}".format(
        run.returncode, run.stderr)


def test_yaml_nested_and_repeated(built):
    # shipment { string tag; repeated parcel cargo; }  -- parcel is a message
    run = _build_run(built, "shipment",
        "#include <iostream>\n"
        "int main() {{\n"
        "    ::shipment a;\n"
        '    a.set_tag("SHP-1");\n'
        "    auto* p1 = a.add_cargo(); p1->set_label(\"box-a\"); p1->set_weight(3);\n"
        "    auto* p2 = a.add_cargo(); p2->set_label(\"box-b\"); p2->set_weight(7);\n"
        "    const std::string y = harpia::yaml::to_yaml(a);\n"
        "    std::cerr << y;\n"
        "    if (y.find(\"cargo:\\n\") == std::string::npos) return 1;\n"
        "    if (y.find(\"  - \") == std::string::npos) return 2;\n"
        '    if (y.find("label: \\"box-a\\"") == std::string::npos) return 3;\n'
        "    ::shipment b;\n"
        "    if (!harpia::yaml::from_yaml(y, &b)) return 4;\n"
        "    if (b.cargo_size() != 2) return 5;\n"
        '    if (b.cargo(0).label() != "box-a" || b.cargo(1).weight() != 7) return 6;\n'
        "    if (a.SerializeAsString() != b.SerializeAsString()) return 7;\n"
        "    return 0;\n"
        "}}\n", extra_pb=("parcel",))
    assert run.returncode == 0, "nested round-trip failed at #{}\n{}".format(
        run.returncode, run.stderr)


def test_yaml_map_roundtrip(built):
    # queen has map<string,string> a, map<string,int> b, map<int,string> c
    run = _build_run(built, "queen",
        "#include <iostream>\n"
        "int main() {{\n"
        "    ::queen a;\n"
        '    (*a.mutable_a())["k1"] = "v1";\n'
        '    (*a.mutable_b())["hits"] = 9;\n'
        "    const std::string y = harpia::yaml::to_yaml(a);\n"
        "    std::cerr << y;\n"
        '    if (y.find("a:\\n") == std::string::npos) return 1;\n'
        '    if (y.find("\\"k1\\": \\"v1\\"") == std::string::npos) return 2;\n'
        '    if (y.find("\\"hits\\": 9") == std::string::npos) return 3;\n'
        "    ::queen b;\n"
        "    if (!harpia::yaml::from_yaml(y, &b)) return 4;\n"
        '    if (b.a().at("k1") != "v1") return 5;\n'
        '    if (b.b().at("hits") != 9) return 6;\n'
        "    if (a.SerializeAsString() != b.SerializeAsString()) return 7;\n"
        "    return 0;\n"
        "}}\n")
    assert run.returncode == 0, "map round-trip failed at #{}\n{}".format(
        run.returncode, run.stderr)
