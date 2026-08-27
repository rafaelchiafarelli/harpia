// main.cpp -- device app -- constructs each outbound message the Infusion Pump publishes
// and prints it as JSON. Extend it with the generated CRUDL DAO / REST
// bindings the same way HarpiaTest/app_example/consumer does.
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
            ::infusion_status m;
            m.set_flow_rate_ml_h(static_cast<float>(jitter(20, 1)));
            m.set_total_volume_infused_ml(static_cast<float>(jitter(120, 4)));
            m.set_drug_library_name("Norepinephrine");
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "infusion_status: " << js << std::endl;
        }
        {
            ::infusion_safety_alert m;
            m.set_active(static_cast<int>(std::llround(jitter(0, 0))));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "infusion_safety_alert: " << js << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Infusion Pump device app: done" << std::endl;
    return 0;
}
