"""Stage 10 -- unified serialization façade + phi redaction (Track F, F.2 & F.3).

`harpia::serialize::to_string(msg, Format)` / `from_string(text, &msg, Format)`
(SerializeAdapter/runtime/harpia_serialize.h) is the single toString path
across JSON/XML/YAML, replacing three separate per-format entry points.

F.2 half:
  - compiles every generated <name>_serialize.h wrapper,
  - round-trips a flat and a nested/repeated non-`phi` message through all
    three formats via the unified path, and
  - proves the refactor is behavior-preserving for JSON: the façade's JSON
    output is byte-identical to protobuf's own MessageToJsonString and to
    what the existing json/<name>_json.h wrapper produces.

F.3 half (SerializeAdapter/runtime/harpia_redaction.h +
generated serialize/harpia_phi_registry.h):
  - a `phi` field renders as the fixed `[REDACTED]` placeholder by default in
    JSON, XML and YAML alike, with the real value nowhere in the output,
  - a message with no `phi` field is byte-for-byte the unchanged engine
    output (the acceptance gate, checked at runtime here and in golden by
    test_golden.py),
  - a mixed message redacts only its `phi` fields,
  - redaction_enabled(false) is the seam F.4 will drive behind
    `--allow-phi-print` -- flipping it restores the real values.

The JSON/XML golden-snapshot acceptance gate (14.5/14.6 unchanged) is covered
by test_golden.py -- SerializeAdapter adds a serialize/ dir and touches none
of the json/ or xml/ wrappers, and redaction lives in the (non-snapshotted)
runtime, not the wrappers.

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


# --------------------------------------------------------------------------
# F.3 -- phi redaction
# --------------------------------------------------------------------------
_REDACT_ALL = r'''
#include <iostream>
using harpia::serialize::Format;
static bool has(const std::string& h, const std::string& n) {
    return h.find(n) != std::string::npos;
}
int main() {
    ::lab_result m;
    m.set_subject_ref("MRN-12345");
    m.set_analyte_code("GLUCOSE");
    m.set_value_scaled(910);
    m.set_reference_high(6.5f);
    const char* leaks[] = {"MRN-12345", "GLUCOSE", "910", "6.500000"};
    for (Format fmt : {Format::JSON, Format::XML, Format::YAML}) {
        const std::string s = harpia::serialize::to_string(m, fmt);
        std::cerr << "[" << harpia::serialize::format_name(fmt) << "] " << s << "\n";
        if (!has(s, "[REDACTED]")) return 10;
        // every phi field's key is still in the structure
        if (!has(s, "subject_ref") || !has(s, "analyte_code")
            || !has(s, "value_scaled") || !has(s, "reference_high")) return 11;
        // and no real value survived, in any of the four types
        for (const char* leak : leaks) if (has(s, leak)) return 12;
    }
    return 0;
}
'''


def test_phi_fields_redacted_in_all_three_formats(built):
    run = _build_run(
        built, "redact_all",
        includes=["serialize/lab_result___HASH___serialize.h"],
        pb_names=["lab_result"],
        body=_REDACT_ALL,
    )
    assert run.returncode == 0, "redaction check failed at code {}\n{}".format(
        run.returncode, run.stdout + run.stderr)


_REDACT_MIXED = r'''
using harpia::serialize::Format;
static bool has(const std::string& h, const std::string& n) {
    return h.find(n) != std::string::npos;
}
int main() {
    ::patient_vitals m;                       // phi: patient_id, heart_rate
    m.set_patient_id("MRN-77");
    m.set_heart_rate(88.0f);
    m.set_device_note("cuff-A");              // NOT phi
    for (Format fmt : {Format::JSON, Format::XML, Format::YAML}) {
        const std::string s = harpia::serialize::to_string(m, fmt);
        if (!has(s, "[REDACTED]")) return 1;
        if (has(s, "MRN-77")) return 2;       // phi string gone
        if (has(s, "88.000000")) return 3;    // phi number gone
        if (!has(s, "cuff-A")) return 4;      // non-phi value kept
        if (!has(s, "device_note")) return 5;
        if (!has(s, "patient_id") || !has(s, "heart_rate")) return 6;
    }
    return 0;
}
'''


def test_mixed_message_redacts_only_phi_fields(built):
    run = _build_run(
        built, "redact_mixed",
        includes=["serialize/patient_vitals___HASH___serialize.h"],
        pb_names=["patient_vitals"],
        body=_REDACT_MIXED,
    )
    assert run.returncode == 0, "mixed-redaction check failed at code {}\n{}".format(
        run.returncode, run.stdout + run.stderr)


_NON_PHI_UNCHANGED = r'''
#include <google/protobuf/util/json_util.h>
using harpia::serialize::Format;
int main() {
    ::parcel m; m.set_label("box"); m.set_weight(4);
    // JSON: identical to the raw protobuf util (redaction path not taken)
    std::string util;
    ::google::protobuf::util::MessageToJsonString(m, &util);
    if (harpia::serialize::to_string(m, Format::JSON) != util) return 1;
    // XML / YAML: identical to the untouched engines
    if (harpia::serialize::to_string(m, Format::XML) != harpia::xml::to_xml(m)) return 2;
    if (harpia::serialize::to_string(m, Format::YAML) != harpia::yaml::to_yaml(m)) return 3;
    return 0;
}
'''


def test_non_phi_message_bypasses_redaction_path(built):
    run = _build_run(
        built, "nonphi_unchanged",
        includes=["serialize/parcel___HASH___serialize.h"],
        pb_names=["parcel"],
        body=_NON_PHI_UNCHANGED,
    )
    assert run.returncode == 0, "non-phi bypass failed at code {}\n{}".format(
        run.returncode, run.stdout + run.stderr)


_TOGGLE = r'''
using harpia::serialize::Format;
static bool has(const std::string& h, const std::string& n) {
    return h.find(n) != std::string::npos;
}
int main() {
    ::lab_result m; m.set_subject_ref("MRN-9"); m.set_analyte_code("NA");
    // default: redacted
    if (!has(harpia::serialize::to_string(m, Format::JSON), "[REDACTED]")) return 1;
    if (has(harpia::serialize::to_string(m, Format::JSON), "MRN-9")) return 2;
    // F.4's seam: turn redaction off -> real values, no placeholder
    harpia::redaction::set_redaction_enabled(false);
    for (Format fmt : {Format::JSON, Format::XML, Format::YAML}) {
        const std::string s = harpia::serialize::to_string(m, fmt);
        if (has(s, "[REDACTED]")) return 3;
        if (!has(s, "MRN-9")) return 4;
    }
    harpia::redaction::set_redaction_enabled(true);
    if (!has(harpia::serialize::to_string(m, Format::JSON), "[REDACTED]")) return 5;
    return 0;
}
'''


def test_redaction_toggle_is_the_f4_seam(built):
    run = _build_run(
        built, "toggle",
        includes=["serialize/lab_result___HASH___serialize.h"],
        pb_names=["lab_result"],
        body=_TOGGLE,
    )
    assert run.returncode == 0, "redaction toggle failed at code {}\n{}".format(
        run.returncode, run.stdout + run.stderr)
