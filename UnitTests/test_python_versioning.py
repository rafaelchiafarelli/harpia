"""python-target / py-versioning task 3: wire-number freezing holds for
Python peers across schema versions (``Message/FieldMap``, no new runtime).

One tiny root schema in a temp dir (its own ``schema_registry/`` next to it --
the committed one is never touched) is generated for Python twice:

    v1  push message reading { int keep; string old_label; float gone; }
    v2  push message reading { string extra; int keep;
                               renamed_from[old_label] string label; }

- numbers: ``keep`` keeps its number, ``label`` inherits ``old_label``'s,
  ``gone``'s number is recorded as reserved in the sidecar and ``extra``
  doesn't reuse it;
- v1 bytes parse in v2 (renamed field keeps its value, the new one is
  default); v2 bytes parse in v1 (the unknown field is tolerated and kept);
  v2 JSON / XML parse in v1 (unknown keys ignored);
- cross-target: a C++ v1 ``reading_sender`` → a Python v2 receiver over
  ZMQ tcp.

v1 and v2 are both ``harpia_generated``, so each side runs in its own
subprocess.
"""
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

V1 = "push message reading{\n    int keep;\n    string old_label;\n    float gone;\n};\n"
V2 = ("push message reading{\n    string extra;\n    int keep;\n"
      "    renamed_from[old_label] string label;\n};\n")


def _generate(root, inc_dir, out):
    env = dict(os.environ, HARPIA_OUTPUT_DIR=out, HARPIA_INPUT_FILE=root,
               HARPIA_INCLUDE_FOLDER=inc_dir, HARPIA_GEN_LANG="python")
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]


@pytest.fixture(scope="module")
def gens(tmp_path_factory):
    d = tmp_path_factory.mktemp("versioning")
    root = d / "root.harpia"
    root.write_text('import "inc.harpia";\n')
    h = hashlib.md5(root.read_bytes()).hexdigest()
    (d / "inc.harpia").write_text(V1)
    _generate(str(root), str(d), str(d / "v1"))
    (d / "inc.harpia").write_text(V2)
    _generate(str(root), str(d), str(d / "v2"))
    return {"dir": d, "hash": h, "v1": str(d / "v1"), "v2": str(d / "v2")}


def _numbers(gen, h):
    proto = open(os.path.join(gen, "python", "proto", "harpia_generated", "protofiles",
                              "reading_%s.proto" % h)).read()
    return {name: int(num) for name, num in re.findall(r"\b(\w+)\s*=\s*(\d+)\s*;", proto)}


def test_numbers_are_frozen(gens):
    v1, v2 = _numbers(gens["v1"], gens["hash"]), _numbers(gens["v2"], gens["hash"])
    assert v2["keep"] == v1["keep"]
    assert v2["label"] == v1["old_label"]
    assert "gone" not in v2 and v1["gone"] not in v2.values()
    assert v2["extra"] not in v1.values()
    fieldmap = open(os.path.join(gens["dir"], "schema_registry", "root",
                                 "reading.fieldmap")).read()
    reserved = re.search(r"^#\s*reserved:\s*(.*)$", fieldmap, re.M).group(1)
    assert str(v1["gone"]) in [t.strip() for t in reserved.split(",")]


_PEER = r'''
import importlib, json, sys
root, h, op, arg = sys.argv[1:5]
sys.path.insert(0, root)
pb2 = importlib.import_module("harpia_generated.protofiles.reading_%s_pb2" % h)
js = importlib.import_module("harpia_runtime.json")
xml = importlib.import_module("harpia_runtime.xml")
fields = [f.name for f in pb2.reading.DESCRIPTOR.fields if f.name in ("keep", "old_label", "gone", "label", "extra")]
if op == "write":
    m = pb2.reading(**json.loads(arg))
    print(json.dumps({"bin": m.SerializeToString().hex(), "json": js.to_json(m), "xml": xml.to_xml(m)}))
else:
    m = pb2.reading()
    if op == "bin":
        m.ParseFromString(bytes.fromhex(arg)); ok = True
    elif op == "json":
        ok = js.from_json(arg, m)
    else:
        ok = xml.from_xml(arg, m)
    print(json.dumps({"ok": bool(ok), "fields": {f: getattr(m, f) for f in fields},
                      "unknown": len(m.SerializeToString()) - len(pb2.reading(**{f: getattr(m, f) for f in fields}).SerializeToString())}))
'''


def _peer(gens, side, op, arg):
    out = subprocess.run([sys.executable, "-c", _PEER, os.path.join(gens[side], "python"),
                          gens["hash"], op, arg if isinstance(arg, str) else json.dumps(arg)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_v1_bytes_parse_in_v2(gens):
    w = _peer(gens, "v1", "write", {"keep": 42, "old_label": "hello", "gone": 1.5})
    r = _peer(gens, "v2", "bin", w["bin"])
    assert r["ok"] and r["fields"] == {"keep": 42, "label": "hello", "extra": ""}
    assert r["unknown"] > 0  # gone's bytes are kept as an unknown field, not misread


def test_v2_bytes_json_xml_parse_in_v1(gens):
    w = _peer(gens, "v2", "write", {"keep": 7, "label": "renamed", "extra": "new"})
    r = _peer(gens, "v1", "bin", w["bin"])
    assert r["ok"] and r["fields"] == {"keep": 7, "old_label": "renamed", "gone": 0.0}
    assert r["unknown"] > 0  # extra tolerated and retained
    for fmt in ("json", "xml"):
        r = _peer(gens, "v1", fmt, w[fmt])
        assert r["ok"], fmt          # unknown keys ignored
        assert r["fields"]["keep"] == 7
        assert r["fields"]["gone"] == 0.0


_CPP = r'''
#include <chrono>
#include <thread>
#include "zmq/reading_%(h)s_zmq.h"
int main(int, char** argv) {
    ::zmq::context_t ctx;
    harpia::zmq_transport::reading_sender s(ctx, argv[1], "cpp-v1");
    s.socket().set(::zmq::sockopt::linger, 2000);
    ::reading r; r.set_keep(99); r.set_old_label("from-cpp-v1"); r.set_gone(2.5f);
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    return s.send(r) ? 0 : 3;
}
'''

_RECV = r'''
import importlib, sys, zmq
root, h, ep = sys.argv[1:4]
sys.path.insert(0, root)
z = importlib.import_module("harpia_generated.zmq.reading_%s_zmq" % h)
ctx = zmq.Context()
rx = z.new_receiver(ctx, ep)
rx.socket.setsockopt(zmq.RCVTIMEO, 15000)
print("READY", flush=True)
m = rx.recv()
print(m.keep, m.label, repr(m.extra), flush=True)
'''


@pytest.mark.skipif(shutil.which("g++") is None or not os.path.exists("/usr/include/zmq.hpp"),
                    reason="needs g++ + cppzmq")
def test_cpp_v1_to_python_v2_over_zmq(gens, tmp_path):
    pytest.importorskip("zmq")
    h = gens["hash"]
    cpp_root = os.path.join(gens["v1"], "generated", "cpp")
    (tmp_path / "s.cpp").write_text(_CPP % {"h": h})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf", "libzmq"],
                           capture_output=True, text=True, check=True).stdout.split()
    exe = tmp_path / "s"
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(tmp_path / "s.cpp"),
                        os.path.join(cpp_root, "protofiles", "reading_%s.pb.cc" % h),
                        "-o", str(exe), *flags, "-lpthread"],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr[-3000:]
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    ep = "tcp://127.0.0.1:%d" % s.getsockname()[1]
    s.close()
    rx = subprocess.Popen([sys.executable, "-c", _RECV, os.path.join(gens["v2"], "python"), h,
                           ep], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert rx.stdout.readline().strip() == "READY"
        run = subprocess.run([str(exe), ep], capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr
        out, err = rx.communicate(timeout=60)
    finally:
        rx.kill()
    assert out.strip() == "99 from-cpp-v1 ''", out + err
