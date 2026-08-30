"""dds-transport epic, task 3 -- OMG DDS-Security wiring for the vendored
Eclipse Cyclone DDS stack.

Whenever a schema declares a `dds` message, `DdsAdapter` ships, next to the
per-message transports:

  dds/harpia_dds_security.h                 hand-written secured-participant
                                            helper (inline CYCLONEDDS_URI
                                            <Security> block; fail-safe --
                                            SecurityRefused, never a silent
                                            plaintext fallback)
  dds/security/governance.xml               static, fail-safe posture
                                            (allow_unauthenticated_participants
                                            = false, join/read/write access
                                            control on)
  dds/security/permissions.xml              rendered: publish + subscribe
                                            allow rules over exactly this
                                            schema's `dds` topic names,
                                            default DENY
  dds/security/dds_security_selection.json  the F5 CryptoBackend choice
                                            (openssl / openssl_fips, driven
                                            by risk_class/topology) + whether
                                            the compliance profile mandates
                                            hardened transport

Two layers:
  - structural / pure Python (always): inspect the emitted files off a real
    pipeline run, plus drive `DdsAdapter` directly to check the F5 selection
    and the no-`dds` case.
  - integration (cmake + g++ + protoc + installed CycloneDDS-CXX + openssl,
    i.e. the Docker image): provision a throwaway PKI with
    Assets/cmake/dds_security_provision.sh, then run a driver that forks a
    secured publisher, a secured subscriber and a *plain* subscriber on one
    domain -- the plain (unauthenticated) peer receives nothing, the secured
    peer receives the stream. "Plaintext/unauthenticated DDS refused by
    default", the task's guarantee.
"""
import glob
import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "dds_security_provision.sh")


# --------------------------------------------------------------------------
# structural -- pure Python, always runs
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dds_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_dds_security")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "build", "generated", "cpp", "dds")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_security_runtime_shipped_verbatim(dds_dir):
    shipped = os.path.join(dds_dir, "harpia_dds_security.h")
    assert os.path.isfile(shipped)
    assert _read(shipped) == _read(os.path.join(
        REPO_ROOT, "DdsAdapter", "runtime", "harpia_dds_security.h"))


def test_security_runtime_is_fail_safe(dds_dir):
    h = _read(os.path.join(dds_dir, "harpia_dds_security.h"))
    # the mechanism, its fail-safe refusal, and the Cyclone-native transport
    assert "class SecurityRefused" in h
    assert "scoped_security_config" in h
    assert "secured_participant" in h
    assert "CYCLONEDDS_URI" in h
    assert "if (!files.complete())" in h and "throw SecurityRefused" in h
    # all three builtin plugins wired (auth + access control + crypto)
    assert "dds_security_auth" in h
    assert "dds_security_ac" in h
    assert "dds_security_crypto" in h


def test_governance_is_strict_and_verbatim(dds_dir):
    gov = os.path.join(dds_dir, "security", "governance.xml")
    assert os.path.isfile(gov)
    text = _read(gov)
    assert text == _read(os.path.join(
        REPO_ROOT, "DdsAdapter", "runtime", "dds_governance.xml"))
    assert "<allow_unauthenticated_participants>false"\
           "</allow_unauthenticated_participants>" in text
    assert "<enable_join_access_control>true</enable_join_access_control>" in text
    assert "<enable_read_access_control>true</enable_read_access_control>" in text
    assert "<enable_write_access_control>true</enable_write_access_control>" in text


def test_permissions_rendered_with_this_schemas_topics(dds_dir):
    perms = _read(os.path.join(dds_dir, "security", "permissions.xml"))
    # both `dds` fixtures, in publish AND subscribe allow rules
    assert perms.count("<topic>alarm_event</topic>") == 2
    assert perms.count("<topic>vitals_publication</topic>") == 2
    # a non-`dds` message must not leak into the grant
    assert "<topic>users</topic>" not in perms
    assert "<topic>courier</topic>" not in perms
    # default-deny, and the subject sentinel the provisioning step fills in
    assert "<default>DENY</default>" in perms
    assert "%HARPIA_SUBJECT_NAME%" in perms


def test_selection_records_the_f5_choice(dds_dir):
    sel = json.loads(_read(os.path.join(
        dds_dir, "security", "dds_security_selection.json")))
    # the repo project.harpia.yaml is class_c / cloud_connected
    assert sel == {
        "hardening_required": True,
        "crypto_backend": "openssl_fips",
        "cmake_package": "OpenSSL",
        "openssl_provider": "fips",
        "fips": True,
    }


def test_selection_follows_compliance_and_backend(tmp_path):
    """Drive DdsAdapter directly with a low-risk profile + an explicit
    standard backend: the selection record must flip."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    from DdsAdapter.DdsAdapter import DdsAdapter
    from Crypto.backend import get_backend
    from Compliance.context import (
        ComplianceContext, PhiHandling, RiskClass, Topology)

    ctx = ComplianceContext(risk_class=RiskClass.CLASS_A,
                            topology=Topology.STANDALONE,
                            phi_handling=PhiHandling.NONE, jurisdiction=[])

    class _Msg:
        name = "vitals_publication"
        md5Hash = "deadbeef"
        isEnum = False
        is_critical = False
        access_modifiers = [("DDS", "dds ")]
        variables = []

    dest = str(tmp_path)
    DdsAdapter(messages=[_Msg()], dest=dest, compliance=ctx,
               crypto_backend=get_backend("openssl")).Process()
    sel = json.loads(_read(os.path.join(
        dest, "generated", "cpp", "dds", "security",
        "dds_security_selection.json")))
    assert sel["hardening_required"] is False
    assert sel["crypto_backend"] == "openssl"
    assert sel["fips"] is False


def test_no_security_dir_without_a_dds_message(tmp_path):
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    from DdsAdapter.DdsAdapter import DdsAdapter

    class _Msg:
        name = "plain"
        md5Hash = "deadbeef"
        isEnum = False
        is_critical = False
        access_modifiers = [("PUSH", "push ")]
        variables = []

    dest = str(tmp_path)
    DdsAdapter(messages=[_Msg()], dest=dest).Process()
    dds = os.path.join(dest, "generated", "cpp", "dds")
    assert not os.path.exists(os.path.join(dds, "harpia_dds_security.h"))
    assert not os.path.exists(os.path.join(dds, "security"))


def test_provisioning_script_present_and_executable():
    assert os.path.isfile(PROVISION)
    assert os.stat(PROVISION).st_mode & stat.S_IXUSR
    body = _read(PROVISION)
    assert "openssl smime -sign" in body           # signs governance/permissions
    assert "%HARPIA_SUBJECT_NAME%" in body          # fills the grant subject
    assert "NEVER for production" in body


# --------------------------------------------------------------------------
# integration -- cmake + g++ + protoc + installed CycloneDDS-CXX + openssl
# --------------------------------------------------------------------------

def _cyclonedds_cxx_findable():
    for root in ("/usr/local", "/usr", os.environ.get("CMAKE_PREFIX_PATH", "")):
        for prefix in filter(None, root.split(os.pathsep)):
            if glob.glob(os.path.join(prefix, "lib*", "cmake", "CycloneDDS-CXX*",
                                     "CycloneDDS-CXX*.cmake")):
                return True
    return False


_gated = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("cmake", "g++", "protoc", "openssl"))
    or not _cyclonedds_cxx_findable(),
    reason="needs cmake + g++ + protoc + openssl + installed CycloneDDS-CXX "
           "(Docker image)",
)

_DRIVER = r"""
// dds-transport task 3 -- DDS-Security refusal proof.
//
// Forks (before any DDS/Cyclone call) a secured publisher, a secured
// subscriber and a PLAIN subscriber on domain 0. The plain, unauthenticated
// peer must receive nothing; the secured peer must receive the stream.
#include <sys/wait.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>

#include "dds/dds.hpp"
#include "dds/harpia_dds_security.h"
#include "dds/alarm_event_@HASH@_dds.h"

using harpia::dds_transport::alarm_event_publisher;
using harpia::dds_transport::alarm_event_subscriber;
using harpia::dds_security::SecurityFiles;
using harpia::dds_security::secured_participant;

static SecurityFiles files_from(const std::string& d) {
  SecurityFiles f;
  f.identity_ca           = d + "/identity_ca.pem";
  f.identity_certificate  = d + "/identity_certificate.pem";
  f.private_key           = d + "/private_key.pem";
  f.permissions_ca        = d + "/permissions_ca.pem";
  f.governance            = d + "/governance.p7s";
  f.permissions           = d + "/permissions.p7s";
  return f;
}

static const int kRunMs = 15000;   // DDS-Security handshake + SEDP + delivery
static const int kPubEveryMs = 200;

static int run_secured_publisher(const std::string& certs) {
  try {
    auto dp = secured_participant(0, files_from(certs));
    alarm_event_publisher pub(dp);
    const auto end = std::chrono::steady_clock::now() +
                     std::chrono::milliseconds(kRunMs);
    int i = 0;
    while (std::chrono::steady_clock::now() < end) {
      ::alarm_event a;
      a.set_patient_id("p-1");
      a.set_alarm_type("apnea");
      a.set_severity(i++);
      pub.publish(a);
      std::this_thread::sleep_for(std::chrono::milliseconds(kPubEveryMs));
    }
    return 0;
  } catch (const std::exception& e) {
    std::fprintf(stderr, "pub: %s\n", e.what());
    return 1;
  }
}

template <typename MakeParticipant>
static int run_subscriber(int wfd, MakeParticipant make) {
  int got = 0;
  try {
    auto dp = make();
    alarm_event_subscriber sub(dp);
    const auto end = std::chrono::steady_clock::now() +
                     std::chrono::milliseconds(kRunMs);
    while (std::chrono::steady_clock::now() < end) {
      ::alarm_event a;
      while (sub.receive(&a)) ++got;
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
  } catch (const std::exception& e) {
    std::fprintf(stderr, "sub: %s\n", e.what());
  }
  char buf[32];
  int n = std::snprintf(buf, sizeof(buf), "%d", got);
  ssize_t w = ::write(wfd, buf, (size_t)n);
  (void)w;
  return 0;
}

int main(int argc, char** argv) {
  if (argc < 2) { std::fprintf(stderr, "usage: %s <certs_dir>\n", argv[0]); return 2; }
  const std::string certs = argv[1];

  int sec_pipe[2], plain_pipe[2];
  if (pipe(sec_pipe) || pipe(plain_pipe)) { std::perror("pipe"); return 2; }

  pid_t pub_pid = fork();
  if (pub_pid == 0) { ::close(sec_pipe[0]); ::close(sec_pipe[1]);
                      ::close(plain_pipe[0]); ::close(plain_pipe[1]);
                      _exit(run_secured_publisher(certs)); }

  pid_t sec_pid = fork();
  if (sec_pid == 0) { ::close(sec_pipe[0]); ::close(plain_pipe[0]); ::close(plain_pipe[1]);
                      _exit(run_subscriber(sec_pipe[1],
                            [&]{ return secured_participant(0, files_from(certs)); })); }

  pid_t plain_pid = fork();
  if (plain_pid == 0) { ::close(plain_pipe[0]); ::close(sec_pipe[0]); ::close(sec_pipe[1]);
                        _exit(run_subscriber(plain_pipe[1],
                              []{ return ::dds::domain::DomainParticipant(0); })); }

  ::close(sec_pipe[1]);
  ::close(plain_pipe[1]);

  auto read_count = [](int fd) {
    std::string s; char c;
    while (::read(fd, &c, 1) == 1) s += c;
    return s.empty() ? -1 : std::atoi(s.c_str());
  };
  int secured_got = read_count(sec_pipe[0]);
  int plain_got = read_count(plain_pipe[0]);

  int st = 0;
  ::waitpid(pub_pid, &st, 0);
  ::waitpid(sec_pid, &st, 0);
  ::waitpid(plain_pid, &st, 0);

  std::printf("DDS_SECURITY secured_got=%d refused_plain_got=%d\n",
              secured_got, plain_got);
  if (plain_got == 0 && secured_got > 0) {
    std::printf("DDS_SECURITY OK\n");
    return 0;
  }
  std::printf("DDS_SECURITY FAIL (expected plain=0, secured>0)\n");
  return 1;
}
"""

_CMAKE = r"""
cmake_minimum_required(VERSION 3.16)
project(harpia_dds_security_demo CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT DEFINED HARPIA_GEN)
  message(FATAL_ERROR "pass -DHARPIA_GEN=<path to build/generated/cpp>")
endif()
find_package(Protobuf REQUIRED)
find_package(CycloneDDS-CXX REQUIRED)
add_subdirectory("${HARPIA_GEN}/dds" "${CMAKE_BINARY_DIR}/dds_gen")
file(GLOB PB_SRCS "${HARPIA_GEN}/protofiles/*.pb.cc")
add_executable(dds_security_demo dds_security_demo.cpp ${PB_SRCS})
target_include_directories(dds_security_demo PRIVATE
  "${HARPIA_GEN}" ${Protobuf_INCLUDE_DIRS})
target_link_libraries(dds_security_demo PRIVATE
  harpia_dds_transport protobuf::libprotobuf)
"""


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_dds_security_gen")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    root = os.path.join(str(out), "build")
    gen_cpp = os.path.join(root, "generated", "cpp")
    pc = subprocess.run(
        ["protoc", "--proto_path=" + os.path.join(root, "proto"),
         "--cpp_out=" + gen_cpp,
         "protofiles/alarm_event_{}.proto".format(HASH)],
        capture_output=True, text=True)
    assert pc.returncode == 0, "protoc failed:\n" + pc.stdout + pc.stderr
    return gen_cpp


@_gated
def test_unauthenticated_dds_peer_is_refused(generated, tmp_path):
    dds_sec = os.path.join(generated, "dds", "security")

    # 1. provision a throwaway PKI + sign the emitted governance/permissions
    certs = tmp_path / "certs"
    prov = subprocess.run(
        ["sh", PROVISION, str(certs),
         os.path.join(dds_sec, "governance.xml"),
         os.path.join(dds_sec, "permissions.xml")],
        capture_output=True, text=True)
    assert prov.returncode == 0, "provision failed:\n" + prov.stdout + prov.stderr
    for f in ("identity_ca.pem", "identity_certificate.pem", "private_key.pem",
              "permissions_ca.pem", "governance.p7s", "permissions.p7s"):
        assert os.path.isfile(certs / f), "provisioning did not produce " + f

    # 2. build the fork-based refusal driver against the generated transport
    src = tmp_path / "proj"
    src.mkdir()
    (src / "dds_security_demo.cpp").write_text(_DRIVER.replace("@HASH@", HASH))
    (src / "CMakeLists.txt").write_text(_CMAKE)
    build = tmp_path / "build"
    cfg = subprocess.run(
        ["cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
         "-DHARPIA_GEN=" + generated],
        capture_output=True, text=True)
    assert cfg.returncode == 0, "configure failed:\n" + cfg.stdout + cfg.stderr
    bld = subprocess.run(
        ["cmake", "--build", str(build), "-j", str(os.cpu_count() or 2)],
        capture_output=True, text=True)
    assert bld.returncode == 0, "build failed:\n" + bld.stdout + bld.stderr

    # 3. run it -- plain peer gets nothing, secured peer gets the stream
    exe = build / "dds_security_demo"
    assert exe.exists()
    run = subprocess.run([str(exe), str(certs)], capture_output=True, text=True,
                         timeout=120)
    out = run.stdout + run.stderr
    # the driver's own exit code + markers are the signal; Cyclone writes
    # async teardown chatter to stderr after "OK" ("Remote secure participant
    # ... not allowed" -- the access-control plugin refusing the plain peer),
    # so don't require OK to be the literal last line.
    assert run.returncode == 0, "security demo failed:\n" + out
    assert "refused_plain_got=0" in out          # plain peer received nothing
    assert "DDS_SECURITY OK" in out
    assert "DDS_SECURITY FAIL" not in out
