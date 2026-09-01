"""transport-authn epic, "zmq-zap-allowlist" -- the ZMQ CURVE ZAP client-key
allowlist.

The shipped CURVE transport is encryption-only: any client with valid CURVE
crypto is accepted. Under a hardened compliance profile the generated
CURVE_SERVER sockets (PULL receiver / PUB publisher) start a ZAP handler
(RFC 27) on inproc://zeromq.zap.01 that consults the HARPIA_ZMQ_ALLOWLIST file
at the handshake -- a client public key that is not on the list is rejected
even with otherwise-valid CURVE crypto. Same predicate as mTLS / RBAC
(transport_hardening_required), never per-jurisdiction; fail-safe deny-all with
no allowlist file; one AuditSink "zap_denied" record per rejected key
(z85 key + identity metadata only, never secret material).

Layers:
  * structural (pure Python): a hardened generation injects
    `::harpia::zap::ensure_running(ctx)` into the CURVE-server apply and copies
    zap/harpia_zap.h (+ harpia_audit_sink.h); a low-risk generation does
    neither (byte-identical to the encryption-only headers).
  * g++ standalone against ZmqAdapter/runtime/harpia_zap.h: AllowList::from_env
    parsing (comments / blanks / identity column), exact-match `contains`,
    missing file -> empty (deny-all).
  * libzmq + cppzmq + protoc gated, real tcp:// (CURVE is a no-op over inproc):
    an allowlisted client key completes the handshake and delivers a message;
    a non-allowlisted key with valid CURVE crypto never does (bounded timeout,
    not a hang); the ZAP handler records exactly the denial, key metadata only.
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
ZAP_SRC = os.path.join(REPO_ROOT, "ZmqAdapter", "runtime", "harpia_zap.h")
ZAP_RUNTIME_DIR = os.path.join(REPO_ROOT, "ZmqAdapter", "runtime")
AUDIT_RUNTIME_DIR = os.path.join(REPO_ROOT, "Compliance", "runtime")
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "zmq_zap_provision.sh")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _have_libzmq():
    if shutil.which("pkg-config") is None:
        return False
    return subprocess.run(["pkg-config", "--exists", "libzmq"]).returncode == 0


def _gen(out_dir, hardened):
    """Run the pipeline into out_dir under a hardened or low-risk profile;
    return the generated/cpp root."""
    env = dict(os.environ)
    if not hardened:
        cfg = os.path.join(out_dir, "low_risk.harpia.yaml")
        os.makedirs(out_dir, exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write("risk_class: class_a\ntopology: standalone\n")
        env["HARPIA_COMPLIANCE_CONFIG"] = cfg
    r = subprocess.run([sys.executable, RUNNER, out_dir],
                       cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(out_dir, "build", "generated", "cpp")


# ==========================================================================
# structural -- pure Python, always runs
# ==========================================================================

def test_hardened_generation_wires_the_zap_handler(tmp_path):
    cpp = _gen(str(tmp_path / "hard"), hardened=True)
    zdir = os.path.join(cpp, "zmq")
    headers = sorted(glob.glob(os.path.join(zdir, "*_zmq.h")))
    assert headers, "no zmq headers generated"

    # every generated header has a bind-side CURVE_SERVER socket -> the include
    # and, in the server ctor(s), the ensure_running() call guarded by CURVE
    for h in headers:
        text = open(h).read()
        assert '#include "zap/harpia_zap.h"' in text, h
        assert "::harpia::zap::ensure_running(ctx);" in text, h
        # only inside the "curve on" branch, right before curve_server is set
        m = re.search(
            r"if \(!curve\.secret_key\.empty\(\)\) \{\s*"
            r"::harpia::zap::ensure_running\(ctx\);\s*"
            r"socket_\.set\(::zmq::sockopt::curve_server, true\);", text)
        assert m, "ensure_running not in the CURVE-server branch of {}".format(h)

    # the runtime + its AuditSink dependency are copied verbatim
    for name, src_dir in (("harpia_zap.h", ZAP_RUNTIME_DIR),
                          ("harpia_audit_sink.h", AUDIT_RUNTIME_DIR)):
        dst = os.path.join(cpp, "zap", name)
        assert os.path.exists(dst), dst
        assert open(dst).read() == open(os.path.join(src_dir, name)).read()


def test_low_risk_generation_is_the_encryption_only_transport(tmp_path):
    cpp = _gen(str(tmp_path / "soft"), hardened=False)
    zdir = os.path.join(cpp, "zmq")
    headers = sorted(glob.glob(os.path.join(zdir, "*_zmq.h")))
    assert headers
    for h in headers:
        text = open(h).read()
        # the header comment describes both modes; assert the actual wiring is
        # absent (no include, no ensure_running call statement).
        assert '#include "zap/harpia_zap.h"' not in text, h
        assert "::harpia::zap::ensure_running(ctx);" not in text, h
    assert not os.path.isdir(os.path.join(cpp, "zap")), "no zap/ dir when soft"


# ==========================================================================
# g++ standalone -- the AllowList mechanism (ZmqAdapter/runtime/harpia_zap.h)
# ==========================================================================

_g = pytest.mark.skipif(
    shutil.which("g++") is None
    or not _have_libzmq()
    or not os.path.exists("/usr/include/zmq.hpp"),
    reason="needs g++ + libzmq + cppzmq")


@_g
def test_allowlist_parsing_and_exact_match(tmp_path):
    listing = tmp_path / "allow.txt"
    listing.write_text(
        "# a comment\n"
        "\n"
        "keyAAA identity-a\n"
        "keyBBB\n"                       # no identity column
        "   keyCCC   identity-c   # trailing comment\n",
        encoding="utf-8")
    src = tmp_path / "al.cpp"
    src.write_text(r'''
#include <cstdlib>
#include <cstdio>
#include "harpia_zap.h"
using harpia::zap::AllowList;
int main() {
    setenv("HARPIA_ZMQ_ALLOWLIST", "%s", 1);
    AllowList a = AllowList::from_env();
    if (a.empty()) return 1;
    if (!a.contains("keyAAA") || !a.contains("keyBBB") || !a.contains("keyCCC")) return 2;
    if (a.contains("keyDDD") || a.contains("key")) return 3;          // exact match only
    if (a.identity("keyAAA") != "identity-a") return 4;
    if (a.identity("keyCCC") != "identity-c") return 5;               // whitespace/comment trimmed
    if (!a.identity("keyBBB").empty()) return 6;                      // no identity column
    // a missing file -> empty list -> deny-all
    setenv("HARPIA_ZMQ_ALLOWLIST", "%s/does-not-exist", 1);
    if (!AllowList::from_env().empty()) return 7;
    // unset -> empty
    unsetenv("HARPIA_ZMQ_ALLOWLIST");
    if (!AllowList::from_env().empty()) return 8;
    return 0;
}
''' % (str(listing), str(tmp_path)), encoding="utf-8")
    binp = tmp_path / "al"
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         "-I", ZAP_RUNTIME_DIR, "-I", AUDIT_RUNTIME_DIR,
         str(src), "-o", str(binp), "-lzmq", "-lpthread"],
        capture_output=True, text=True)
    assert c.returncode == 0, c.stdout + c.stderr
    r = subprocess.run([str(binp)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, "AllowList check #{}".format(r.returncode)


# ==========================================================================
# integration -- the generated transport under a hardened profile, real tcp://
# ==========================================================================

_live = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("protoc", "g++", "pkg-config"))
    or not _have_libzmq()
    or not os.path.exists("/usr/include/zmq.hpp"),
    reason="needs protoc + g++ + libzmq + cppzmq (harpia Docker image)")


def _pkgconfig(*args):
    out = subprocess.run(["pkg-config", *args, "protobuf", "libzmq"],
                         capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


@pytest.fixture(scope="module")
def hardened_zmq(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_zap")
    cpp = _gen(str(out), hardened=True)
    build = os.path.join(str(out), "build")
    from ProtoFile.ProtoCompiler import ProtoCompiler
    assert ProtoCompiler(dest=build).Process() is None, "Stage 7 failed"
    return {"cpp_root": cpp, "tmp": str(out),
            "proto_dir": os.path.join(cpp, "protofiles")}


_KEYPAIR = (
    "static bool keypair(std::string* pub, std::string* sec) {\n"
    "    char p[41], s[41];\n"
    "    if (zmq_curve_keypair(p, s) != 0) return false;\n"
    "    *pub = p; *sec = s; return true;\n"
    "}\n"
)


def _build(hz, name, body):
    prog = os.path.join(hz["tmp"], name + ".cc")
    with open(prog, "w") as f:
        f.write(
            '#include "zmq/users_{h}_zmq.h"\n'
            "#include <zmq.h>\n"
            "#include <cstdlib>\n"
            "#include <fstream>\n"
            "#include <string>\n"
            "#include <thread>\n"
            "#include <chrono>\n".format(h=HASH)
            + _KEYPAIR + body)
    pb_cc = os.path.join(hz["proto_dir"], "users_{}.pb.cc".format(HASH))
    binary = os.path.join(hz["tmp"], name)
    c = subprocess.run(
        ["g++", "-std=c++17", "-I", hz["cpp_root"], *_pkgconfig("--cflags"),
         prog, pb_cc, "-o", binary, *_pkgconfig("--libs"), "-lpthread"],
        capture_output=True, text=True, timeout=180)
    assert c.returncode == 0, "{} failed to build:\n{}".format(name, c.stderr)
    return binary


@_live
def test_allowlisted_key_passes_unknown_key_is_refused(hardened_zmq):
    binary = _build(hardened_zmq, "zap_live", r'''
int main(int argc, char** argv) {
    // argv[1] = mode ("allow" | "deny"); argv[2] = a writable dir for the
    // allowlist file (keeps it out of the CWD / repo tree).
    const std::string mode = argc > 1 ? argv[1] : "allow";
    const std::string dir  = argc > 2 ? argv[2] : ".";
    std::string spub, ssec, cpub, csec;
    if (!keypair(&spub, &ssec) || !keypair(&cpub, &csec)) return 10;
    // write the allowlist BEFORE the first ensure_running() reads it
    const std::string al = dir + "/zap_allow_" + mode + ".txt";
    { std::ofstream o(al);
      if (mode == "allow") o << cpub << " tester\n";
      else o << "rZ8dOtNormalKeyHere000000000000000000000 other\n"; }
    setenv("HARPIA_ZMQ_ALLOWLIST", al.c_str(), 1);

    ::zmq::context_t ctx{1};
    harpia::zmq_transport::CurveServerKeys skeys{ssec};
    harpia::zmq_transport::users_receiver rcv(ctx, "tcp://127.0.0.1:*", skeys);
    rcv.socket().set(::zmq::sockopt::linger, 0);
    rcv.socket().set(::zmq::sockopt::rcvtimeo, 2500);
    std::string ep = rcv.socket().get(::zmq::sockopt::last_endpoint);

    harpia::zmq_transport::CurveClientKeys ckeys{spub, cpub, csec};
    harpia::zmq_transport::users_sender snd(ctx, ep, "zap-test", ckeys);
    snd.socket().set(::zmq::sockopt::linger, 0);
    ::users out; out.set_name("neo"); out.set_address("matrix");
    if (!snd.send(out)) return 1;
    ::users in;
    const bool got = rcv.recv(&in);
    if (mode == "allow")  return (got && in.name() == "neo") ? 0 : 2;
    else                  return got ? 3 : 0;
}
''')
    for mode in ("allow", "deny"):
        r = subprocess.run([binary, mode, hardened_zmq["tmp"]],
                           capture_output=True, text=True, timeout=40)
        assert r.returncode == 0, "{} case failed (rc={})".format(mode, r.returncode)


@_live
def test_zap_handler_audits_each_denial_key_metadata_only(hardened_zmq):
    binary = _build(hardened_zmq, "zap_audit", r'''
#include <atomic>
#include <mutex>
struct CountingSink : ::harpia::compliance::AuditSink {
    std::atomic<int> denials{0};
    std::mutex m;
    std::string last;
    void record(const std::string& op, const std::string&,
                const std::string& detail) override {
        if (op != "zap_denied") return;
        ++denials;
        std::lock_guard<std::mutex> lk(m);
        last = detail;
    }
};
int main() {
    std::string spub, ssec, cpub, csec;
    if (!keypair(&spub, &ssec) || !keypair(&cpub, &csec)) return 10;
    unsetenv("HARPIA_ZMQ_ALLOWLIST");             // no allowlist -> deny-all

    ::zmq::context_t ctx{1};
    CountingSink sink;
    harpia::zap::ZapHandler zh(ctx, sink);        // owns inproc://zeromq.zap.01
    if (!zh.active()) return 9;

    harpia::zmq_transport::CurveServerKeys skeys{ssec};
    harpia::zmq_transport::users_receiver rcv(ctx, "tcp://127.0.0.1:*", skeys);
    rcv.socket().set(::zmq::sockopt::linger, 0);
    rcv.socket().set(::zmq::sockopt::rcvtimeo, 1500);
    std::string ep = rcv.socket().get(::zmq::sockopt::last_endpoint);

    harpia::zmq_transport::CurveClientKeys ckeys{spub, cpub, csec};
    harpia::zmq_transport::users_sender snd(ctx, ep, "mallory", ckeys);
    snd.socket().set(::zmq::sockopt::linger, 0);
    ::users out; out.set_name("mallory");
    (void)snd.send(out);
    ::users in;
    (void)rcv.recv(&in);                          // denied -> times out
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    if (sink.denials.load() < 1) return 1;
    std::lock_guard<std::mutex> lk(sink.m);
    if (sink.last.find("key=") == std::string::npos) return 2;
    if (sink.last.find(cpub) == std::string::npos) return 3;   // the z85 public key
    if (sink.last.find(csec) != std::string::npos) return 4;   // never a secret
    if (sink.last.find(ssec) != std::string::npos) return 5;
    return 0;
}
''')
    r = subprocess.run([binary], capture_output=True, text=True, timeout=40)
    assert r.returncode == 0, "audit check #{}".format(r.returncode)


def test_provision_script_is_present_and_executable():
    assert os.path.isfile(PROVISION) and os.access(PROVISION, os.X_OK)
