// human_mock.cpp -- human-mock -- simulates normal human and operator behaviour for the
// Mechanical Ventilator, emitting a physiologically plausible stream of its
// outbound messages as harpia-generated protobuf, printed as JSON.
//
// Consumes harpia-generated code as a black box. Generate a project from this
// folder first (see README.md); CMake writes harpia_generated_includes.h into
// the build tree from the generated message headers (protofiles/*.pb.h), so no
// md5 hash needs to be spelled out here.
#include "harpia_generated_includes.h"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <random>
#include <string>
#include <thread>

#include <google/protobuf/util/json_util.h>

int main() {
    std::mt19937 rng(20260825u);
    auto jitter = [&](double mean, double sd) {
        if (sd <= 0.0) return mean;
        std::normal_distribution<double> d(mean, sd);
        return d(rng);
    };

    // Default JSON options: proto3 omits fields left at their zero value, so a
    // quiet alarm message prints as "{}" -- realistic for "nothing to report".
    ::google::protobuf::util::JsonPrintOptions jopts;

    const int iterations = 20;
    for (int i = 0; i < iterations; ++i) {
        {
            ::ventilation_metrics m;
            m.set_tidal_volume_ml(static_cast<float>(jitter(450, 25)));
            m.set_airway_pressure_cmh2o(static_cast<float>(jitter(18, 3)));
            m.set_fio2_percent(static_cast<float>(jitter(40, 2)));
            m.set_respiration_frequency_bpm(static_cast<float>(jitter(14, 1)));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "ventilation_metrics: " << js << std::endl;
        }
        {
            ::disconnect_alarm m;
            m.set_alarm_code(static_cast<int>(std::llround(jitter(0, 0))));
            m.set_is_disconnected(static_cast<int>(std::llround(jitter(0, 0))));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "disconnect_alarm: " << js << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Mechanical Ventilator human-mock: done" << std::endl;
    return 0;
}
