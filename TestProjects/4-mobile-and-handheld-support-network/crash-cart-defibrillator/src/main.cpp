// main.cpp -- device app -- constructs each outbound message the Crash Cart Defibrillator publishes
// and prints it as JSON. Extend it with the generated CRUDL DAO / REST
// bindings the same way examples/consumer does.
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

    const int iterations = 1;
    for (int i = 0; i < iterations; ++i) {
        {
            ::defib_ecg m;
            m.set_patient_id("PT-ER-01");
            for (int k = 0; k < 8; ++k) m.add_ecg_samples(static_cast<float>(jitter(0.0, 1.0)));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "defib_ecg: " << js << std::endl;
        }
        {
            ::shock_event m;
            m.set_energy_joules(static_cast<float>(jitter(200, 0)));
            m.set_pacing_active(static_cast<int>(std::llround(jitter(0, 0))));
            m.set_epoch_millis(static_cast<int>(std::llround(jitter(1731000000, 0))));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "shock_event: " << js << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Crash Cart Defibrillator device app: done" << std::endl;
    return 0;
}
