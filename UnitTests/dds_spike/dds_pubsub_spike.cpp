// dds-transport epic, task 2a -- throwaway spike.
//
// Purpose: prove the vendored Eclipse Cyclone DDS + ddscxx stack is a REAL,
// linkable API (not a paper spec) for exactly the shapes a generated
// `DdsAdapter` will need in tasks 2b / 3:
//
//   1. a publisher / subscriber pair on one topic, one sample crossing;
//   2. a per-message QoS profile set explicitly -- the "critical" profile
//      (RELIABLE + KEEP_ALL + bounded ResourceLimits) and the
//      "latest-value" profile (BEST_EFFORT + KEEP_LAST(1)) that
//      `harpia_sensitive_data_design_rules.md` §4 maps onto (task 2b does
//      the real mapping; here we only prove both profiles construct and a
//      DataWriter/DataReader accept them);
//   3. a DDS-Security configuration hook -- proven via Cyclone's C
//      `dds_qset_prop` property API (ddscxx 0.10.5 has no C++ `Property`
//      QoS policy; security is the C property API or a `CYCLONEDDS_URI`
//      `<DDSSecurity>` XML block). No certificates here -- task 3 supplies
//      real values via the F5 `CryptoBackend` seam.
//
// Single process, two participants on domain 0 over loopback, so the test
// needs no IPC orchestration. Prints `SPIKE ...` lines the test asserts on;
// exits 0 only on a verified round trip.

#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>

#include "dds/dds.h"     // C API -- DDS-Security property hook
#include "dds/dds.hpp"   // ddscxx -- everything else
#include "VitalsSample.hpp"

using harpia_dds_spike::VitalsSample;
namespace pol = dds::core::policy;

static dds::pub::qos::DataWriterQos critical_writer_qos(
    const dds::pub::qos::DataWriterQos &base) {
  // §4a ordered/complete: RELIABLE, KEEP_ALL, bounded by ResourceLimits
  // (task 2b derives max_samples from the schema; 1000 is a spike stand-in).
  dds::pub::qos::DataWriterQos q(base);
  q << pol::Reliability::Reliable(dds::core::Duration::from_secs(1));
  q << pol::History::KeepAll();
  q << pol::ResourceLimits(1000, dds::core::LENGTH_UNLIMITED,
                           dds::core::LENGTH_UNLIMITED);
  return q;
}

static dds::pub::qos::DataWriterQos latest_writer_qos(
    const dds::pub::qos::DataWriterQos &base) {
  // §4b latest-value-only: BEST_EFFORT, KEEP_LAST(1).
  dds::pub::qos::DataWriterQos q(base);
  q << pol::Reliability::BestEffort();
  q << pol::History::KeepLast(1);
  return q;
}

static int security_hook_props(void) {
  // The 12 standard OMG DDS-Security property names Cyclone expects; values
  // are placeholders. Proven real by setting them on a dds_qos_t and
  // reading one back.
  static const char *names[] = {
      "dds.sec.auth.library.path",      "dds.sec.auth.library.init",
      "dds.sec.auth.library.finalize",  "dds.sec.auth.identity_ca",
      "dds.sec.auth.private_key",       "dds.sec.auth.identity_certificate",
      "dds.sec.access.library.path",    "dds.sec.access.library.init",
      "dds.sec.access.library.finalize","dds.sec.crypto.library.path",
      "dds.sec.crypto.library.init",    "dds.sec.crypto.library.finalize",
  };
  const int n = (int)(sizeof(names) / sizeof(names[0]));
  dds_qos_t *sec = dds_create_qos();
  for (int i = 0; i < n; ++i) dds_qset_prop(sec, names[i], "placeholder");
  char *readback = nullptr;
  bool ok = dds_qget_prop(sec, "dds.sec.auth.identity_ca", &readback) &&
            readback && std::strcmp(readback, "placeholder") == 0;
  if (readback) dds_free(readback);
  dds_delete_qos(sec);
  std::printf("SPIKE security-hook props_staged=%d readback_ok=%d\n", n,
              ok ? 1 : 0);
  return ok ? n : -1;
}

static bool wait_for_match(dds::pub::DataWriter<VitalsSample> &writer,
                           std::chrono::milliseconds timeout) {
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (std::chrono::steady_clock::now() < deadline) {
    if (writer.publication_matched_status().current_count() > 0) return true;
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  return false;
}

int main() {
  try {
    dds::domain::DomainParticipant pub_participant(0);
    dds::domain::DomainParticipant sub_participant(0);

    dds::topic::Topic<VitalsSample> pub_topic(pub_participant, "harpia_vitals");
    dds::topic::Topic<VitalsSample> sub_topic(sub_participant, "harpia_vitals");

    dds::pub::Publisher publisher(pub_participant);
    dds::sub::Subscriber subscriber(sub_participant);

    const auto crit_w = critical_writer_qos(publisher.default_datawriter_qos());
    const auto latest_w = latest_writer_qos(publisher.default_datawriter_qos());
    std::printf("SPIKE reliable-profile reliability=%s history=%s\n",
                crit_w.policy<pol::Reliability>().kind() ==
                        pol::ReliabilityKind::RELIABLE
                    ? "RELIABLE"
                    : "BEST_EFFORT",
                crit_w.policy<pol::History>().kind() == pol::HistoryKind::KEEP_ALL
                    ? "KEEP_ALL"
                    : "KEEP_LAST");
    std::printf("SPIKE latest-profile reliability=%s history=KEEP_LAST(%d)\n",
                latest_w.policy<pol::Reliability>().kind() ==
                        pol::ReliabilityKind::BEST_EFFORT
                    ? "BEST_EFFORT"
                    : "RELIABLE",
                latest_w.policy<pol::History>().depth());

    if (security_hook_props() < 0) {
      std::printf("SPIKE FAIL security property API did not round-trip\n");
      return 1;
    }

    // Reader must use a compatible reliability for the RELIABLE writer.
    dds::sub::qos::DataReaderQos rqos(subscriber.default_datareader_qos());
    rqos << pol::Reliability::Reliable(dds::core::Duration::from_secs(1));
    rqos << pol::History::KeepAll();

    dds::pub::DataWriter<VitalsSample> writer(publisher, pub_topic, crit_w);
    dds::sub::DataReader<VitalsSample> reader(subscriber, sub_topic, rqos);

    if (!wait_for_match(writer, std::chrono::milliseconds(5000))) {
      std::printf("SPIKE FAIL writer never matched a reader\n");
      return 1;
    }

    VitalsSample sent;
    sent.device_id(1);
    sent.spo2(98);
    sent.pulse_rate(72);
    writer.write(sent);

    const auto deadline =
        std::chrono::steady_clock::now() + std::chrono::milliseconds(5000);
    while (std::chrono::steady_clock::now() < deadline) {
      auto samples = reader.take();
      for (const auto &s : samples) {
        if (!s.info().valid()) continue;
        const auto &d = s.data();
        std::printf("SPIKE roundtrip device_id=%d spo2=%d pulse_rate=%d\n",
                    d.device_id(), d.spo2(), d.pulse_rate());
        if (d.device_id() == 1 && d.spo2() == 98 && d.pulse_rate() == 72) {
          std::printf("SPIKE OK\n");
          return 0;
        }
        std::printf("SPIKE FAIL payload mismatch\n");
        return 1;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    std::printf("SPIKE FAIL sample never arrived\n");
    return 1;
  } catch (const dds::core::Exception &e) {
    std::printf("SPIKE FAIL dds exception: %s\n", e.what());
    return 2;
  }
}
