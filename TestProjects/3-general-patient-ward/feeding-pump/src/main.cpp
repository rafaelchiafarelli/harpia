// main.cpp -- device app -- constructs each outbound message the Feeding Pump publishes
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
            ::feeding_status m;
            m.set_feed_rate_ml_h(static_cast<float>(jitter(60, 3)));
            m.set_total_volume_delivered_ml(static_cast<float>(jitter(300, 6)));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "feeding_status: " << js << std::endl;
        }
        {
            ::feeding_block_alert m;
            m.set_active(static_cast<int>(std::llround(jitter(0, 0))));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "feeding_block_alert: " << js << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Feeding Pump device app: done" << std::endl;
    return 0;
}
