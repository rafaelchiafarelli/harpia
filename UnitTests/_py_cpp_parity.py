"""Shared harness (not a test module) for the Python-target serialization
parity tests (python-target / py-serialization): the Python runtimes must
match the C++ runtimes byte-for-byte (XML/YAML/redacted) or by cross-parse
(JSON).

- ``generate_python(tmp)`` generates the HarpiaTest fixture with
  ``HARPIA_GEN_LANG=python`` (the C++ pipeline runs too).
- ``probe(gen)`` builds ONE C++ program linking every generated ``.pb.cc``,
  ``harpia_xml.h``, ``harpia_yaml.h`` and ``harpia_serialize.h`` (cached per
  generation dir, objects compiled in parallel). It reads ``<op> <type>
  <hex|->`` lines on stdin and answers ``OK|FAIL <hex>`` per line. Ops:
  ``to_json to_xml to_yaml xsd ser_json ser_xml ser_yaml`` take a binary
  message; ``from_json from_xml from_yaml`` take text and answer the parsed
  binary; ``redact_off`` / ``redact_on`` flip the C++ redaction toggle.
- ``run(gen, requests)`` drives it.
- ``fixture_messages(py_root)`` imports every generated ``_pb2`` module and
  returns ``{full_name: class}``; ``populate(msg)`` fills a message
  reflectively with deterministic values that stress escaping (one entry
  per map: C++ map iteration order is unspecified, so multi-entry maps
  can't be byte-compared).
"""
import concurrent.futures
import functools
import glob
import importlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests._java_gradle_helpers import generate  # noqa: E402


def _importable(*mods):
    try:
        for m in mods:
            importlib.import_module(m)
        return True
    except ImportError:
        return False


HAVE_PY = (all(shutil.which(t) for t in ("protoc", "grpc_python_plugin"))
           and _importable("google.protobuf", "grpc"))
HAVE_CPP = HAVE_PY and all(shutil.which(t) for t in ("g++", "pkg-config"))
SKIP_PY = "needs protoc + grpc_python_plugin + python protobuf/grpcio (harpia image)"
SKIP_CPP = SKIP_PY + " + g++ + pkg-config protobuf"

STRESS = 'v"<&\'>\\\n\té-'


def generate_python(tmp):
    return generate(tmp, lang="python")


def py_root(gen):
    return os.path.join(gen, "python")


def fixture_messages(root):
    """Import every generated _pb2 module; return {full_name: message class}."""
    if root not in sys.path:
        sys.path.insert(0, root)
    out = {}
    for f in sorted(glob.glob(os.path.join(root, "harpia_generated", "protofiles",
                                           "*_pb2.py"))):
        mod = importlib.import_module("harpia_generated.protofiles." +
                                      os.path.basename(f)[:-3])
        for d in mod.DESCRIPTOR.message_types_by_name.values():
            out[d.full_name] = getattr(mod, d.name)
    return out


def populate(msg, depth=0, seen=()):
    """Fill every field with a deterministic value (recursive, cycle-safe)."""
    from google.protobuf.descriptor import FieldDescriptor as FD
    d = msg.DESCRIPTOR
    if d.full_name in seen or depth > 3:
        return msg
    seen = seen + (d.full_name,)
    for f in d.fields:
        n = f.number
        is_map = (f.type == FD.TYPE_MESSAGE and f.message_type.GetOptions().map_entry)
        if is_map:
            kf, vf = f.message_type.fields_by_name["key"], f.message_type.fields_by_name["value"]
            key = _scalar(kf, n)
            container = getattr(msg, f.name)
            if vf.cpp_type == FD.CPPTYPE_MESSAGE:
                populate(container[key], depth + 1, seen)
            else:
                container[key] = _scalar(vf, n + 1)
        elif f.label == FD.LABEL_REPEATED:
            container = getattr(msg, f.name)
            for k in range(2):
                if f.cpp_type == FD.CPPTYPE_MESSAGE:
                    populate(container.add(), depth + 1, seen)
                else:
                    container.append(_scalar(f, n + k))
        elif f.cpp_type == FD.CPPTYPE_MESSAGE:
            sub = getattr(msg, f.name)
            sub.SetInParent()
            populate(sub, depth + 1, seen)
        else:
            setattr(msg, f.name, _scalar(f, n))
    return msg


def _scalar(f, n):
    from google.protobuf.descriptor import FieldDescriptor as FD
    t = f.cpp_type
    if t == FD.CPPTYPE_INT32:
        return -(n * 7 + 1) if n % 2 else n * 7 + 1
    if t == FD.CPPTYPE_INT64:
        return 9007199254740993 + n  # > 2**53: int64-as-string matters
    if t == FD.CPPTYPE_UINT32:
        return 4000000000 + n
    if t == FD.CPPTYPE_UINT64:
        return 18000000000000000000 + n
    if t == FD.CPPTYPE_DOUBLE:
        return n + 0.5
    if t == FD.CPPTYPE_FLOAT:
        return n + 0.25
    if t == FD.CPPTYPE_BOOL:
        return True
    if t == FD.CPPTYPE_ENUM:
        return f.enum_type.values[-1].number
    if t == FD.CPPTYPE_STRING:
        if f.type == FD.TYPE_BYTES:
            return (f.name + STRESS).encode()
        return f.name + STRESS
    raise AssertionError(f.full_name)


_PROBE_SRC = r'''
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <google/protobuf/descriptor.h>
#include <google/protobuf/message.h>
#include <google/protobuf/util/json_util.h>
#include "xml/harpia_xml.h"
#include "yaml/harpia_yaml.h"
#include "serialize/harpia_serialize.h"

namespace gp = ::google::protobuf;

static std::string unhex(const std::string& h) {
    std::string out;
    for (size_t i = 0; i + 1 < h.size(); i += 2)
        out += static_cast<char>(std::stoi(h.substr(i, 2), nullptr, 16));
    return out;
}
static std::string hex(const std::string& s) {
    static const char* x = "0123456789abcdef";
    std::string out;
    for (unsigned char c : s) { out += x[c >> 4]; out += x[c & 15]; }
    return out;
}

int main() {
    using harpia::serialize::Format;
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream ss(line);
        std::string op, type, arg;
        ss >> op >> type >> arg;
        if (op == "redact_off") { harpia::redaction::set_redaction_enabled(false); std::cout << "OK \n" << std::flush; continue; }
        if (op == "redact_on") { harpia::redaction::set_redaction_enabled(true); std::cout << "OK \n" << std::flush; continue; }
        const gp::Descriptor* d = gp::DescriptorPool::generated_pool()->FindMessageTypeByName(type);
        if (!d) { std::cout << "FAIL notype\n" << std::flush; continue; }
        std::unique_ptr<gp::Message> m(gp::MessageFactory::generated_factory()->GetPrototype(d)->New());
        const std::string in = (arg == "-" || arg.empty()) ? std::string() : unhex(arg);
        std::string out;
        bool ok = true;
        if (op.rfind("from_", 0) != 0 && op != "xsd") ok = m->ParseFromString(in);
        if (op == "to_json") ok = ok && gp::util::MessageToJsonString(*m, &out).ok();
        else if (op == "to_xml") out = harpia::xml::to_xml(*m);
        else if (op == "to_yaml") out = harpia::yaml::to_yaml(*m);
        else if (op == "xsd") out = harpia::xml::xsd(d);
        else if (op == "ser_json") out = harpia::serialize::to_string(*m, Format::JSON);
        else if (op == "ser_xml") out = harpia::serialize::to_string(*m, Format::XML);
        else if (op == "ser_yaml") out = harpia::serialize::to_string(*m, Format::YAML);
        else if (op == "from_json") { ok = harpia::serialize::from_string(in, m.get(), Format::JSON); out = m->SerializeAsString(); }
        else if (op == "from_xml") { ok = harpia::serialize::from_string(in, m.get(), Format::XML); out = m->SerializeAsString(); }
        else if (op == "from_yaml") { ok = harpia::serialize::from_string(in, m.get(), Format::YAML); out = m->SerializeAsString(); }
        else ok = false;
        std::cout << (ok ? "OK " : "FAIL ") << hex(out) << "\n" << std::flush;
    }
    return 0;
}
'''


def _pkgconfig(flag):
    return subprocess.run(["pkg-config", flag, "protobuf"], capture_output=True,
                          text=True, check=True).stdout.split()


@functools.lru_cache(maxsize=None)
def probe(gen):
    """Build (once per generation dir) and return the probe binary path."""
    cpp_root = os.path.join(gen, "generated", "cpp")
    tinyxml = os.path.join(REPO_ROOT, "third_party", "tinyxml2")
    work = os.path.join(gen, "_parity_build")
    os.makedirs(work, exist_ok=True)
    src = os.path.join(work, "probe.cc")
    with open(src, "w") as f:
        f.write(_PROBE_SRC)
    sources = sorted(s for s in glob.glob(os.path.join(cpp_root, "protofiles", "*.pb.cc"))
                     if not s.endswith(".grpc.pb.cc"))
    sources += [os.path.join(tinyxml, "tinyxml2.cpp"), src]
    cflags = ["-std=c++17", "-O0", "-I", cpp_root, "-I", tinyxml] + _pkgconfig("--cflags")

    def _compile(s):
        obj = os.path.join(work, os.path.basename(s) + ".o")
        r = subprocess.run(["g++", *cflags, "-c", s, "-o", obj],
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, "{}:\n{}".format(s, r.stderr)
        return obj

    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as ex:
        objs = list(ex.map(_compile, sources))
    exe = os.path.join(work, "probe")
    r = subprocess.run(["g++", *objs, "-o", exe, *_pkgconfig("--libs"), "-pthread"],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    return exe


def run(gen, requests):
    """requests: [(op, type, payload bytes|None)] -> [(ok, bytes)]"""
    lines = "".join("{} {} {}\n".format(op, typ or "-",
                                        payload.hex() if payload else "-")
                    for op, typ, payload in requests)
    r = subprocess.run([probe(gen)], input=lines, capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stderr
    out = []
    for line in r.stdout.splitlines():
        status, _, h = line.partition(" ")
        out.append((status == "OK", bytes.fromhex(h.strip()) if status == "OK" else h))
    assert len(out) == len(requests), r.stdout[-500:]
    return out
