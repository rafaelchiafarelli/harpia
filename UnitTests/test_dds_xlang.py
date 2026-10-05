"""python-target / tri-language-interop task 5: DDS between C++ and Python,
the two DDS-capable targets. **Java has no DDS** (not in the Java target's
scope), so it takes no part here.

One python-target generation (C++ + Python, same hash). Each language runs
the same peer CLI in its own process -- the C++ one built with
``UnitTests/py_dds_interop/CMakeLists.txt`` over a test-written driver, the
Python one a script over the generated modules (a DDS-Security participant
is per process, item 36):

    pub <message> <topic> <domain> <certs|->      hex frames on stdin, then
                                                  EOF; waits for a match,
                                                  publishes them in order
    sub <message> <topic> <domain> <certs|-> <n> <stall> <run_s>
                                                  READY; with stall=1 waits
                                                  for a GO line first; prints
                                                  GOT <hex> per sample

for every ``dds`` message (``alarm_event`` -- critical: reliable, keep-all;
``vitals_publication`` -- best-effort, keep-last(1)):

- **cross delivery**: C++ -> Python and Python -> C++, populated messages
  (stress strings, every field) compared whole; critical delivers every
  sample in order, best-effort an in-order subset;
- **QoS across languages**: the subscriber of the *other* language stalls
  while 20 samples are published, then drains: critical holds all 20 in
  order, non-critical collapses to at most the newest one;
- **DDS-Security**: a secured publisher of each language, with a secured
  C++ and a secured Python subscriber (both get every sample) and a plain C++
  and a plain Python subscriber (both get nothing) on the same domain, over
  one ``dds_security_provision.sh`` PKI on the generated governance /
  permissions documents (the real topic names: permissions name them).

Gated on cmake + g++ + CycloneDDS-CXX, the cyclonedds Python binding, openssl
and the Python toolchain.
"""
import os
import random
import shutil
import subprocess
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests.test_dds_demo import _cyclonedds_cxx_findable  # noqa: E402
from UnitTests.test_py_dds import _have_cyclonedds_py  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "dds_security_provision.sh")
COUNTER = {"alarm_event": "severity", "vitals_publication": "pulse_rate"}
CRITICAL = {"alarm_event"}
LANGS = ("cpp", "python")

pytestmark = pytest.mark.skipif(
    not (P.HAVE_PY and _have_cyclonedds_py() and shutil.which("cmake") and shutil.which("g++")
         and shutil.which("openssl") and _cyclonedds_cxx_findable()),
    reason="needs cmake + g++ + CycloneDDS-CXX, the cyclonedds binding, openssl and the "
           "Python toolchain (image)")

_CPP = r'''
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include "dds/dds.hpp"
#include "dds/harpia_dds_security.h"
#include "dds/alarm_event_@HASH@_dds.h"
#include "dds/vitals_publication_@HASH@_dds.h"

using namespace harpia::dds_transport;
using clk = std::chrono::steady_clock;

static std::string unhex(const std::string& h) {
  std::string out;
  for (size_t i = 0; i + 1 < h.size(); i += 2)
    out += static_cast<char>(std::stoi(h.substr(i, 2), nullptr, 16));
  return out;
}

static std::string hex(const std::string& b) {
  static const char* d = "0123456789abcdef";
  std::string out;
  for (unsigned char c : b) { out += d[c >> 4]; out += d[c & 15]; }
  return out;
}

template <typename Pub, typename Msg>
static int publish(Pub& pub) {
  std::vector<std::string> frames;
  std::string line;
  while (std::getline(std::cin, line)) if (!line.empty()) frames.push_back(line);
  const auto deadline = clk::now() + std::chrono::seconds(25);
  while (pub.matched_subscribers() == 0 && clk::now() < deadline)
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  if (pub.matched_subscribers() == 0) { std::printf("NOMATCH\n"); return 1; }
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  for (const auto& f : frames) {
    Msg m;
    if (!m.ParseFromString(unhex(f))) return 3;
    pub.publish(m);
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  std::this_thread::sleep_for(std::chrono::milliseconds(1000));
  std::printf("PUB_DONE\n");
  return 0;
}

template <typename Sub, typename Msg>
static int subscribe(Sub& sub, int n, bool stall, int run_s) {
  std::printf("READY\n");
  std::fflush(stdout);
  if (stall) { std::string go; std::getline(std::cin, go); }
  int got = 0;
  const auto deadline = clk::now() + std::chrono::seconds(run_s);
  auto last = clk::now();
  while (got < n && clk::now() < deadline) {
    Msg m;
    if (sub.receive(&m)) {
      std::printf("GOT %s\n", hex(m.SerializeAsString()).c_str());
      std::fflush(stdout);
      ++got;
      last = clk::now();
    } else {
      if (stall && clk::now() - last > std::chrono::seconds(1)) break;
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
  }
  std::printf("SUB_DONE %d\n", got);
  return 0;
}

static ::dds::domain::DomainParticipant participant(uint32_t domain, const std::string& c) {
  if (c == "-") return ::dds::domain::DomainParticipant(domain);
  harpia::dds_security::SecurityFiles f;
  f.identity_ca = c + "/identity_ca.pem";
  f.identity_certificate = c + "/identity_certificate.pem";
  f.private_key = c + "/private_key.pem";
  f.permissions_ca = c + "/permissions_ca.pem";
  f.governance = c + "/governance.p7s";
  f.permissions = c + "/permissions.p7s";
  return harpia::dds_security::secured_participant(domain, f);
}

int main(int argc, char** argv) {
  if (argc < 6) return 2;
  const std::string mode = argv[1], type = argv[2], topic = argv[3];
  auto dp = participant(static_cast<uint32_t>(std::atoi(argv[4])), argv[5]);
  if (mode == "pub") {
    if (type == "alarm_event") {
      alarm_event_publisher p(dp, topic);
      return publish<alarm_event_publisher, ::alarm_event>(p);
    }
    vitals_publication_publisher p(dp, topic);
    return publish<vitals_publication_publisher, ::vitals_publication>(p);
  }
  const int n = std::atoi(argv[6]), run_s = std::atoi(argv[8]);
  const bool stall = std::string(argv[7]) == "1";
  if (type == "alarm_event") {
    alarm_event_subscriber s(dp, topic);
    return subscribe<alarm_event_subscriber, ::alarm_event>(s, n, stall, run_s);
  }
  vitals_publication_subscriber s(dp, topic);
  return subscribe<vitals_publication_subscriber, ::vitals_publication>(s, n, stall, run_s);
}
'''

_PY = r'''
import glob, importlib, os, sys, time
root, mode, name, topic, domain, certs, *rest = sys.argv[1:]
sys.path.insert(0, root)
stem = os.path.basename(glob.glob(os.path.join(
    root, "harpia_generated", "dds", name + "_*_dds.py"))[0])[:-3]
mod = importlib.import_module("harpia_generated.dds." + stem)
cls = getattr(importlib.import_module("harpia_generated.protofiles." + stem[:-4] + "_pb2"), name)
from cyclonedds.domain import DomainParticipant
from harpia_runtime.dds import security as S
if certs == "-":
    dp = DomainParticipant(int(domain))
else:
    dp = S.secured_participant(int(domain), S.SecurityFiles(*(os.path.join(certs, f) for f in (
        "identity_ca.pem", "identity_certificate.pem", "private_key.pem",
        "permissions_ca.pem", "governance.p7s", "permissions.p7s"))))
if mode == "pub":
    frames = [cls.FromString(bytes.fromhex(l)) for l in sys.stdin.read().split()]
    pub = getattr(mod, name + "_publisher")(dp, topic)
    end = time.monotonic() + 25
    while pub.matched_subscribers() == 0 and time.monotonic() < end:
        time.sleep(0.02)
    if pub.matched_subscribers() == 0:
        print("NOMATCH", flush=True)
        sys.exit(1)
    time.sleep(0.3)
    for m in frames:
        pub.publish(m)
        time.sleep(0.02)
    time.sleep(1.0)
    print("PUB_DONE", flush=True)
else:
    n, stall, run_s = int(rest[0]), rest[1] == "1", float(rest[2])
    sub = getattr(mod, name + "_subscriber")(dp, topic)
    print("READY", flush=True)
    if stall:
        sys.stdin.readline()
    got, end = 0, time.monotonic() + run_s
    while got < n and time.monotonic() < end:
        m = sub.receive(1.0 if stall else 0.1)
        if m is not None:
            print("GOT", m.SerializeToString().hex(), flush=True)
            got += 1
        elif stall:
            break
    print("SUB_DONE", got, flush=True)
'''


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("dds_x"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture(scope="module")
def msgs(gen):
    return P.fixture_messages(P.py_root(gen))


@pytest.fixture(scope="module")
def cpp_peer(gen, tmp_path_factory):
    src = tmp_path_factory.mktemp("dds_x_peer")
    shutil.copy(os.path.join(HERE, "py_dds_interop", "CMakeLists.txt"), str(src))
    (src / "dds_peer.cpp").write_text(_CPP.replace("@HASH@", HASH))
    build = src / "build"
    cfg = subprocess.run(["cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                          "-DHARPIA_GEN=" + os.path.join(gen, "generated", "cpp"),
                          "-DHARPIA_HASH=" + HASH], capture_output=True, text=True)
    assert cfg.returncode == 0, cfg.stdout + cfg.stderr
    bld = subprocess.run(["cmake", "--build", str(build), "-j", str(os.cpu_count() or 2)],
                         capture_output=True, text=True)
    assert bld.returncode == 0, bld.stdout[-3000:] + bld.stderr[-3000:]
    return str(build / "dds_peer")


@pytest.fixture(scope="module")
def certs(gen, tmp_path_factory):
    sec = os.path.join(P.py_root(gen), "harpia_generated", "dds", "security")
    out = str(tmp_path_factory.mktemp("dds_x_pki"))
    p = subprocess.run(["sh", PROVISION, out, os.path.join(sec, "governance.xml"),
                        os.path.join(sec, "permissions.xml")], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return out


class Peers:
    def __init__(self, gen, cpp_peer):
        self.root, self.cpp = P.py_root(gen), cpp_peer

    def cmd(self, lang, *args):
        if lang == "cpp":
            return [self.cpp, *map(str, args)]
        return [sys.executable, "-c", _PY, self.root, *map(str, args)]

    def sub(self, lang, name, topic, domain, certs="-", n=100, stall=False, run_s=20):
        proc = subprocess.Popen(self.cmd(lang, "sub", name, topic, domain, certs, n,
                                         int(stall), run_s),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        assert proc.stdout.readline().strip() == "READY", proc.stderr.read()
        return proc

    def pub(self, lang, name, topic, domain, frames, certs="-"):
        r = subprocess.run(self.cmd(lang, "pub", name, topic, domain, certs),
                           input="".join(m.SerializeToString().hex() + "\n" for m in frames),
                           capture_output=True, text=True, timeout=90)
        assert "PUB_DONE" in r.stdout, r.stdout + r.stderr

    @staticmethod
    def received(proc, cls, go=False):
        out, err = proc.communicate(input="GO\n" if go else None, timeout=90)
        assert "SUB_DONE" in out, out + err
        return [cls.FromString(bytes.fromhex(line.split()[1]))
                for line in out.splitlines() if line.startswith("GOT ")]


@pytest.fixture(scope="module")
def peers(gen, cpp_peer):
    return Peers(gen, cpp_peer)


def _frames(cls, name, n):
    out = []
    for i in range(1, n + 1):
        m = P.populate(cls())
        setattr(m, COUNTER[name], i)
        out.append(m)
    return out


def _topic(name):
    return "%s_%s" % (name, uuid.uuid4().hex[:12])


@pytest.mark.parametrize("name", sorted(COUNTER))
@pytest.mark.parametrize("pub_lang,sub_lang", [("cpp", "python"), ("python", "cpp")])
def test_cross_delivery(name, pub_lang, sub_lang, peers, msgs):
    cls, topic, domain = msgs[name], _topic(name), random.randint(1, 200)
    frames = _frames(cls, name, 10)
    sub = peers.sub(sub_lang, name, topic, domain, n=10, run_s=20)
    try:
        peers.pub(pub_lang, name, topic, domain, frames)
    finally:
        got = peers.received(sub, cls)
    if name in CRITICAL:
        assert got == frames
    else:
        idx = [getattr(m, COUNTER[name]) for m in got]
        assert got and idx == sorted(idx) and all(m == frames[i - 1] for i, m in zip(idx, got))


@pytest.mark.parametrize("name", sorted(COUNTER))
@pytest.mark.parametrize("pub_lang,sub_lang", [("cpp", "python"), ("python", "cpp")])
def test_stalled_reader_qos_across_languages(name, pub_lang, sub_lang, peers, msgs):
    cls, topic, domain = msgs[name], _topic(name), random.randint(1, 200)
    frames = _frames(cls, name, 20)
    sub = peers.sub(sub_lang, name, topic, domain, n=100, stall=True, run_s=30)
    try:
        peers.pub(pub_lang, name, topic, domain, frames)  # nobody drains meanwhile
    finally:
        got = peers.received(sub, cls, go=True)
    if name in CRITICAL:  # reliable + keep-all: the reader kept every sample
        assert got == frames
    else:  # best-effort + keep-last(1): collapsed to (at most) the newest
        assert len(got) <= 1 and all(m == frames[-1] for m in got)


@pytest.mark.parametrize("pub_lang", LANGS)
def test_secured_interop_and_plain_peers_get_nothing(pub_lang, peers, msgs, certs):
    name = "alarm_event"  # permissions name the real topics
    cls, domain = msgs[name], random.randint(1, 200)
    frames = _frames(cls, name, 5)
    subs = {(lang, kind): peers.sub(lang, name, name, domain,
                                    certs if kind == "secured" else "-", n=5,
                                    run_s=20 if kind == "secured" else 12)
            for lang in LANGS for kind in ("secured", "plain")}
    try:
        peers.pub(pub_lang, name, name, domain, frames, certs=certs)
    finally:
        got = {k: peers.received(p, cls) for k, p in subs.items()}
    for lang in LANGS:
        assert got[lang, "secured"] == frames, (pub_lang, lang)
        assert got[lang, "plain"] == [], (pub_lang, lang)
