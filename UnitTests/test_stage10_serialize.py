"""Stage 10 -- unified serialization façade (Track F / Session F.2).

`harpia::serialize::to_string(msg, Format)` / `from_string(text, &msg, Format)`
(SerializeAdapter/runtime/harpia_serialize.h) is the single toString path
across JSON/XML/YAML, replacing three separate per-format entry points. This:

  - compiles every generated <name>_serialize.h wrapper,
  - round-trips a flat and a nested/repeated non-`phi` message through all
    three formats via the unified path, and
  - proves the refactor is behavior-preserving for JSON: the façade's JSON
    output is byte-identical to protobuf's own MessageToJsonString and to
    what the existing json/<name>_json.h wrapper produces.

The JSON/XML golden-snapshot acceptance gate (14.5/14.6 unchanged) is covered
by test_golden.py -- SerializeAdapter adds a new serialize/ dir and touches
none of the json/ or xml/ wrappers.

Skipped unless protoc + g++ + pkg-config(protobuf) are present.
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
    out = tmp_path_factory.mktemp("harpia_serialize")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    from ProtoFile.ProtoCompiler import ProtoCompiler
    build = os.path.join(str(out), "build")
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"

    cpp_root = os.path.join(build, "generated", "cpp")
    return {
        "cpp_root": cpp_root,
        "ser_dir": os.path.join(cpp_root, "serialize"),
        "proto_dir": os.path.join(cpp_root, "protofiles"),
        "tinyxml2": os.path.join(REPO_ROOT, "third_party", "tinyxml2"),
        "tmp": str(out),
    }


def _wrappers(ser_dir):
    return sorted(w for w in glob.glob(os.path.join(ser_dir, "*_serialize.h"))
                  if os.path.basename(w) != "harpia_serialize.h")


def _name_of(wrapper):
    return os.path.basename(wrapper)[:-len("_{}_serialize.h".format(HASH))]


def _build_run(built, tag, body, includes, pb_names, timeout=30):
    """Compile `body` verbatim (only `__HASH__` is substituted) against the
    given includes + pb.cc's + tinyxml2, then run it."""
    def _inc(h):
        h = h.replace("__HASH__", HASH)
        return "#include {}\n".format(h if h.startswith("<") else '"{}"'.format(h))

    src = os.path.join(built["tmp"], "ser_{}.cc".format(tag))
    with open(src, "w") as f:
        f.write("".join(_inc(h) for h in includes))
        f.write(body.replace("__HASH__", HASH))
    pb_ccs = [os.path.join(built["proto_dir"], "{}_{}.pb.cc".format(n, HASH))
              for n in pb_names]
    tinyxml = os.path.join(built["tinyxml2"], "tinyxml2.cpp")
    binary = os.path.join(built["tmp"], "ser_{}".format(tag))
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", built["tinyxml2"],
         *_pkgconfig("--cflags"), src, *pb_ccs, tinyxml, "-o", binary,
         *_pkgconfig("--libs")],
        capture_output=True, text=True, timeout=300,
    )
    assert c.returncode == 0, "{} failed to build:\n{}".format(tag, c.stderr)
    return subprocess.run([binary], capture_output=True, text=True, timeout=timeout)


def test_every_serialize_wrapper_compiles(built):
    wrappers = _wrappers(built["ser_dir"])
    assert wrappers, "no serialization wrappers generated"
    cflags = _pkgconfig("--cflags")
    for wrapper in wrappers:
        name = _name_of(wrapper)
        tu = os.path.join(built["tmp"], "useser_{}.cc".format(name))
        with open(tu, "w") as f:
            f.write(
                '#include "serialize/{}"\n'.format(os.path.basename(wrapper)) +
                "void use() {\n"
                "    using harpia::serialize::Format;\n"
                "    ::" + name + " m;\n"
                "    for (Format fmt : {Format::JSON, Format::XML, Format::YAML}) {\n"
                "        const std::string s = harpia::serialize::to_string(m, fmt);\n"
                "        ::" + name + " b;\n"
                "        (void)harpia::serialize::from_string(s, &b, fmt);\n"
                "    }\n"
                "}\n"
            )
        r = subprocess.run(
            ["g++", "-std=c++17", "-I", built["cpp_root"], "-I", built["tinyxml2"],
             *cflags, "-c", tu, "-o", os.devnull],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, "{} serialize wrapper failed to compile:\n{}".format(
            name, r.stderr)


_ROUNDTRIP = r'''
#include <iostream>
using harpia::serialize::Format;
int main() {
    ::users u; u.set_name("neo"); u.set_address("zion : 1");
    u.set_id___HASH__(42);
    ::shipment s; s.set_tag("SHP-1");
    auto* p = s.add_cargo(); p->set_label("box <a>"); p->set_weight(3);
    auto* q = s.add_cargo(); q->set_label("b\"c"); q->set_weight(7);
    for (Format fmt : {Format::JSON, Format::XML, Format::YAML}) {
        const std::string su = harpia::serialize::to_string(u, fmt);
        if (su.empty()) return 10;
        ::users u2;
        if (!harpia::serialize::from_string(su, &u2, fmt)) return 11;
        if (u.SerializeAsString() != u2.SerializeAsString()) return 12;
        const std::string ss = harpia::serialize::to_string(s, fmt);
        if (ss.empty()) return 20;
        ::shipment s2;
        if (!harpia::serialize::from_string(ss, &s2, fmt)) return 21;
        if (s.SerializeAsString() != s2.SerializeAsString()) return 22;
    }
    std::cout << "ok\n";
    return 0;
}
'''


def test_roundtrip_all_three_formats(built):
    # users (flat) and shipment+parcel (nested + repeated) -- both non-phi.
    run = _build_run(
        built, "roundtrip",
        includes=["serialize/users___HASH___serialize.h",
                  "serialize/shipment___HASH___serialize.h"],
        pb_names=["users", "shipment", "parcel"],
        body=_ROUNDTRIP,
    )
    assert run.returncode == 0, "round-trip failed at code {}\n{}".format(
        run.returncode, run.stdout + run.stderr)
    assert run.stdout.strip() == "ok"


_JSON_PARITY = r'''
using harpia::serialize::Format;
int main() {
    ::parcel m;
    m.set_label("crate-9"); m.set_weight(5);
    const std::string via_facade = harpia::serialize::to_string(m, Format::JSON);
    std::string via_util;
    ::google::protobuf::util::MessageToJsonString(m, &via_util);
    std::string via_wrapper;
    harpia::json::to_json(m, &via_wrapper);
    if (via_facade != via_util) return 1;
    if (via_facade != via_wrapper) return 2;
    ::parcel b;
    if (!harpia::serialize::from_string(via_facade, &b, Format::JSON)) return 3;
    if (m.SerializeAsString() != b.SerializeAsString()) return 4;
    return 0;
}
'''


def test_json_path_is_behavior_preserving(built):
    # the façade's JSON must be byte-identical to protobuf's own util AND to
    # what the pre-existing json/<name>_json.h wrapper emits.
    run = _build_run(
        built, "jsonparity",
        includes=["serialize/parcel___HASH___serialize.h",
                  "json/parcel___HASH___json.h",
                  "<google/protobuf/util/json_util.h>"],
        pb_names=["parcel"],
        body=_JSON_PARITY,
    )
    assert run.returncode == 0, "json parity failed at code {}\n{}".format(
        run.returncode, run.stdout + run.stderr)


_ROBUST = r'''
using harpia::serialize::Format;
int main() {
    ::telemetry def;                       // all defaults, empty repeated
    ::telemetry full;
    full.set_label("L"); full.add_samples(1); full.add_samples(2);
    full.add_notes("a: b"); full.add_notes("<x>\"y\"");
    for (Format fmt : {Format::JSON, Format::XML, Format::YAML}) {
        if (harpia::serialize::to_string(def, fmt).empty()) return 1;
        const std::string s = harpia::serialize::to_string(full, fmt);
        if (s.empty()) return 2;
        if (fmt != Format::JSON && s.find("label") == std::string::npos) return 3;
        ::telemetry b;
        if (!harpia::serialize::from_string(s, &b, fmt)) return 4;
        if (full.SerializeAsString() != b.SerializeAsString()) return 5;
    }
    return 0;
}
'''


def test_never_crashes_and_keeps_structure(built):
    run = _build_run(
        built, "robust",
        includes=["serialize/telemetry___HASH___serialize.h"],
        pb_names=["telemetry", "trace_row"],
        body=_ROBUST,
    )
    assert run.returncode == 0, "robustness check failed at code {}\n{}".format(
        run.returncode, run.stdout + run.stderr)
