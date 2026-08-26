// main.cpp -- device app -- constructs each outbound message the Endoscopy Video Tower publishes
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
            ::video_stream_status m;
            m.set_fps(static_cast<int>(std::llround(jitter(50, 0))));
            m.set_resolution_label("1920x1080");
            m.set_light_source_output_percent(static_cast<float>(jitter(70, 5)));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "video_stream_status: " << js << std::endl;
        }
        {
            ::surgical_snapshot m;
            m.set_snapshot_id("SNAP-001");
            m.set_case_id("CASE-42");
            m.set_caption("survey view");
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "surgical_snapshot: " << js << std::endl;
        }
        {
            ::light_source_stats m;
            m.set_lamp_hours(static_cast<float>(jitter(220, 0)));
            m.set_output_percent(static_cast<float>(jitter(70, 5)));
            m.set_temperature_c(static_cast<float>(jitter(45, 3)));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "light_source_stats: " << js << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Endoscopy Video Tower device app: done" << std::endl;
    return 0;
}
