"""dds-transport epic, task 4 -- a `phi` field crossing the DDS transport
triggers the same `AuditSink` call pattern the db-encryption epic established
for the DB path (`phi_create` / `phi_read` / ...): the transport changes, the
audit obligation does not.

A `dds` message that carries at least one `phi` field (Foundation F2) gets a
`<name>_publisher` that:

  - takes an `::harpia::compliance::AuditSink&` as a trailing ctor parameter,
    defaulted to `::harpia::compliance::default_audit_sink()` -- so a `dds`
    message with no `phi` field, and any untagged project, is byte-identical
    to the pre-task-4 output;
  - records exactly one value-free entry per `publish()`:
    operation `"phi_publish"`, subject = the DDS topic name, detail = the
    comma-joined `phi` field *names* -- never a value (design-rules Rule 5).

`harpia_audit_sink.h` is copied next to the generated `dds/` headers whenever
any emitted `dds` message has a `phi` field.

Two layers, like the DB tests:
  - structural / pure Python (always runs): inspect the generated `dds/`
    headers off a real pipeline run.
  - integration (cmake + g++ + protoc + installed CycloneDDS-CXX, i.e. the
    Docker image): build a driver against the generated publisher + a
    recording `AuditSink`, publish N times, assert exactly N value-free
    `record("phi_publish", <topic>, <names>)` calls -- the
    `test_stage8_db.py::test_a3_*` shape for DDS.
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


# --------------------------------------------------------------------------
# structural -- pure Python, always runs
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dds_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_dds_phi_audit")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "build", "generated", "cpp", "dds")


def _read(d, name):
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return f.read()


def _publisher_half(header):
    """The text of the `<name>_publisher` class only (up to, not including,
    the `<name>_subscriber` that follows it)."""
    start = header.index("_publisher {")
    end = header.index("_subscriber {", start)
    return header[start:end]


def _subscriber_half(header):
    return header[header.index("_subscriber {"):]


# alarm_event: `critical event dds` + `phi string patient_id`
# vitals_publication: plain `dds` + `phi string patient_ref`
PHI_CASES = [
    ("alarm_event", "patient_id"),
    ("vitals_publication", "patient_ref"),
]


@pytest.mark.parametrize("msg,phi_field", PHI_CASES)
def test_phi_publisher_takes_a_defaulted_audit_sink(dds_dir, msg, phi_field):
    pub = _publisher_half(_read(dds_dir, "{}_{}_dds.h".format(msg, HASH)))
    assert ("::harpia::compliance::AuditSink& audit = "
            "::harpia::compliance::default_audit_sink()") in pub
    assert "::harpia::compliance::AuditSink& audit_;" in pub


@pytest.mark.parametrize("msg,phi_field", PHI_CASES)
def test_phi_publish_records_one_value_free_entry(dds_dir, msg, phi_field):
    pub = _publisher_half(_read(dds_dir, "{}_{}_dds.h".format(msg, HASH)))
    call = 'audit_.record("phi_publish", "{topic}", "{names}");'.format(
        topic=msg, names=phi_field)
    assert call in pub
    # exactly one record() call in the publish path
    assert pub.count("audit_.record(") == 1
    # it sits after the actual write, not before it
    assert pub.index("writer_.write(frame);") < pub.index("audit_.record(")


@pytest.mark.parametrize("msg,phi_field", PHI_CASES)
def test_audit_sink_header_included(dds_dir, msg, phi_field):
    header = _read(dds_dir, "{}_{}_dds.h".format(msg, HASH))
    assert '#include "harpia_audit_sink.h"' in header


@pytest.mark.parametrize("msg,phi_field", PHI_CASES)
def test_subscriber_half_is_not_audited(dds_dir, msg, phi_field):
    """task 4 is scoped to the publish side only (operation `phi_publish`).
    The `<name>_subscriber` must be untouched -- no AuditSink member, no
    record() call, no `phi_receive`."""
    sub = _subscriber_half(_read(dds_dir, "{}_{}_dds.h".format(msg, HASH)))
    assert "AuditSink" not in sub
    assert "audit_" not in sub
    assert "record(" not in sub
    assert "phi_receive" not in sub


def test_audit_sink_header_copied_verbatim(dds_dir):
    copied = _read(dds_dir, "harpia_audit_sink.h")
    with open(os.path.join(REPO_ROOT, "Compliance", "runtime",
                           "harpia_audit_sink.h"), encoding="utf-8") as f:
        assert copied == f.read()


def test_no_phi_dds_message_is_byte_identical(tmp_path):
    """Both checked-in `dds` fixtures carry a `phi` field, so drive the
    adapter directly with one that does not: no AuditSink anywhere, and
    harpia_audit_sink.h is not copied into the output at all."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    from DdsAdapter.DdsAdapter import DdsAdapter

    class _Msg:
        name = "plain_stream"
        md5Hash = "deadbeef"
        isEnum = False
        is_critical = False
        access_modifiers = [("DDS", "dds ")]
        variables = []

    dest = str(tmp_path)
    assert DdsAdapter(messages=[_Msg()], dest=dest).Process() is None
    out = os.path.join(dest, "generated", "cpp", "dds")
    header = _read(out, "plain_stream_deadbeef_dds.h")
    assert "AuditSink" not in header
    assert "audit_" not in header
    assert "record(" not in header
    assert "harpia_audit_sink.h" not in header
    assert not os.path.exists(os.path.join(out, "harpia_audit_sink.h"))


# --------------------------------------------------------------------------
# integration -- cmake + g++ + protoc + installed CycloneDDS-CXX (Docker image)
# --------------------------------------------------------------------------

def _cyclonedds_cxx_findable():
    for root in ("/usr/local", "/usr", os.environ.get("CMAKE_PREFIX_PATH", "")):
        for prefix in filter(None, root.split(os.pathsep)):
            if glob.glob(os.path.join(prefix, "lib*", "cmake", "CycloneDDS-CXX*",
                                     "CycloneDDS-CXX*.cmake")):
                return True
    return False


_gated = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("cmake", "g++", "protoc"))
    or not _cyclonedds_cxx_findable(),
    reason="needs cmake + g++ + protoc + installed CycloneDDS-CXX (Docker image)",
)

# publish this many times per message; the driver asserts one record() each.
_N = 5
# a deliberately identifiable `phi` value -- the driver proves it never
# reaches the sink (Rule 5).
_SECRET = "SECRET-PHI-VALUE-42"

_DRIVER = r"""
#include <cstdio>
#include <string>
#include <vector>

#include "dds/dds.hpp"
#include "dds/alarm_event_@HASH@_dds.h"
#include "dds/vitals_publication_@HASH@_dds.h"

using harpia::dds_transport::alarm_event_publisher;
using harpia::dds_transport::vitals_publication_publisher;

struct Rec { std::string op, subject, detail; };

struct RecordingSink : ::harpia::compliance::AuditSink {
  std::vector<Rec> calls;
  void record(const std::string& op, const std::string& subject,
              const std::string& detail = "") override {
    calls.push_back({op, subject, detail});
  }
};

static const int kN = @N@;
static const char* kSecret = "@SECRET@";

static int check(const RecordingSink& s, const char* topic, const char* names) {
  if ((int)s.calls.size() != kN) return 1;
  for (const auto& c : s.calls) {
    if (c.op != "phi_publish") return 2;
    if (c.subject != topic) return 3;
    if (c.detail != names) return 4;              // field NAMES only
    if (c.op.find(kSecret) != std::string::npos ||
        c.subject.find(kSecret) != std::string::npos ||
        c.detail.find(kSecret) != std::string::npos) return 5;  // Rule 5
  }
  return 0;
}

int main() {
  try {
    ::dds::domain::DomainParticipant dp(0);

    RecordingSink crit_sink;
    alarm_event_publisher crit_pub(dp, "alarm_event", crit_sink);
    for (int i = 0; i < kN; ++i) {
      ::alarm_event a;
      a.set_patient_id(kSecret);
      a.set_alarm_type("apnea");
      a.set_severity(i);
      if (!crit_pub.publish(a)) { std::printf("DDS_PHI_AUDIT FAIL publish\n"); return 10; }
    }
    if (int e = check(crit_sink, "alarm_event", "patient_id")) {
      std::printf("DDS_PHI_AUDIT FAIL alarm_event check=%d\n", e); return 20 + e;
    }

    RecordingSink best_sink;
    vitals_publication_publisher best_pub(dp, "vitals_publication", best_sink);
    for (int i = 0; i < kN; ++i) {
      ::vitals_publication v;
      v.set_patient_ref(kSecret);
      v.set_spo2(90 + i);
      v.set_pulse_rate(i);
      if (!best_pub.publish(v)) { std::printf("DDS_PHI_AUDIT FAIL publish\n"); return 11; }
    }
    if (int e = check(best_sink, "vitals_publication", "patient_ref")) {
      std::printf("DDS_PHI_AUDIT FAIL vitals_publication check=%d\n", e); return 40 + e;
    }

    // the default-sink overload still exists and does not blow up
    alarm_event_publisher plain_pub(dp);
    ::alarm_event a; a.set_patient_id("x");
    plain_pub.publish(a);

    std::printf("DDS_PHI_AUDIT OK\n");
    return 0;
  } catch (const ::dds::core::Exception& e) {
    std::printf("DDS_PHI_AUDIT FAIL dds exception: %s\n", e.what());
    return 2;
  }
}
"""

_CMAKE = r"""
cmake_minimum_required(VERSION 3.16)
project(harpia_dds_phi_audit CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT DEFINED HARPIA_GEN)
  message(FATAL_ERROR "pass -DHARPIA_GEN=<path to build/generated/cpp>")
endif()
find_package(Protobuf REQUIRED)
find_package(CycloneDDS-CXX REQUIRED)
add_subdirectory("${HARPIA_GEN}/dds" "${CMAKE_BINARY_DIR}/dds_gen")
file(GLOB PB_SRCS "${HARPIA_GEN}/protofiles/*.pb.cc")
add_executable(dds_phi_audit dds_phi_audit.cpp ${PB_SRCS})
target_include_directories(dds_phi_audit PRIVATE
  "${HARPIA_GEN}" ${Protobuf_INCLUDE_DIRS})
target_link_libraries(dds_phi_audit PRIVATE
  harpia_dds_transport protobuf::libprotobuf)
"""


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_dds_phi_audit_gen")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    root = os.path.join(str(out), "build")
    gen_cpp = os.path.join(root, "generated", "cpp")
    protos = ["protofiles/{}_{}.proto".format(n, HASH)
              for n in ("alarm_event", "vitals_publication")]
    pc = subprocess.run(
        ["protoc", "--proto_path=" + os.path.join(root, "proto"),
         "--cpp_out=" + gen_cpp, *protos],
        capture_output=True, text=True,
    )
    assert pc.returncode == 0, "protoc failed:\n" + pc.stdout + pc.stderr
    return gen_cpp


@_gated
def test_phi_over_dds_emits_one_value_free_audit_record_per_publish(
        generated, tmp_path):
    src = tmp_path / "proj"
    src.mkdir()
    (src / "dds_phi_audit.cpp").write_text(
        _DRIVER.replace("@HASH@", HASH).replace("@N@", str(_N))
               .replace("@SECRET@", _SECRET))
    (src / "CMakeLists.txt").write_text(_CMAKE)

    build = tmp_path / "build"
    cfg = subprocess.run(
        ["cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
         "-DHARPIA_GEN=" + generated],
        capture_output=True, text=True,
    )
    assert cfg.returncode == 0, "configure failed:\n" + cfg.stdout + cfg.stderr

    bld = subprocess.run(
        ["cmake", "--build", str(build), "-j", str(os.cpu_count() or 2)],
        capture_output=True, text=True,
    )
    assert bld.returncode == 0, "build failed:\n" + bld.stdout + bld.stderr

    exe = build / "dds_phi_audit"
    assert exe.exists()
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=90)
    out = run.stdout + run.stderr
    assert run.returncode == 0, "driver failed:\n" + out
    assert out.strip().endswith("DDS_PHI_AUDIT OK")
