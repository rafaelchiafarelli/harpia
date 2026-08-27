// human_mock.cpp -- human-mock -- simulates normal human and operator behaviour for the
// Heart-Lung Machine, emitting a physiologically plausible stream of its
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
            ::perfusion_metrics m;
            m.set_blood_flow_l_min(static_cast<float>(jitter(4.5, 0.3)));
            m.set_blood_temperature_c(static_cast<float>(jitter(34, 0.5)));
            m.set_oxygenation_percent(static_cast<float>(jitter(99, 0.4)));
            m.set_system_pressure_mmhg(static_cast<float>(jitter(200, 15)));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "perfusion_metrics: " << js << std::endl;
        }
        {
            ::perfusion_safety_alarm m;
            m.set_alarm_code(static_cast<int>(std::llround(jitter(0, 0))));
            m.set_pressure_mmhg(static_cast<float>(jitter(200, 15)));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "perfusion_safety_alarm: " << js << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Heart-Lung Machine human-mock: done" << std::endl;
    return 0;
}
