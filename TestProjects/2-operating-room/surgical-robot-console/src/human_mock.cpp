// human_mock.cpp -- human-mock -- simulates normal human and operator behaviour for the
// Surgical Robot Console, emitting a physiologically plausible stream of its
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
            ::arm_telemetry m;
            m.set_arm_id("arm-1");
            m.set_x(static_cast<float>(jitter(0, 5)));
            m.set_y(static_cast<float>(jitter(0, 5)));
            m.set_z(static_cast<float>(jitter(0, 5)));
            m.set_roll(static_cast<float>(jitter(0, 10)));
            m.set_pitch(static_cast<float>(jitter(0, 10)));
            m.set_yaw(static_cast<float>(jitter(0, 10)));
            m.set_instrument_cycle_count(static_cast<int>(std::llround(jitter(5, 0))));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "arm_telemetry: " << js << std::endl;
        }
        {
            ::video_feed_status m;
            m.set_fps(static_cast<int>(std::llround(jitter(60, 0))));
            m.set_bitrate_kbps(static_cast<int>(std::llround(jitter(12000, 500))));
            m.set_resolution_label("1920x1080");
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "video_feed_status: " << js << std::endl;
        }
        {
            ::calibration_status m;
            m.set_subsystem("arm-1");
            m.set_passed(static_cast<int>(std::llround(jitter(1, 0))));
            std::string js;
            (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
            std::cout << "calibration_status: " << js << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    std::cout << "Surgical Robot Console human-mock: done" << std::endl;
    return 0;
}
