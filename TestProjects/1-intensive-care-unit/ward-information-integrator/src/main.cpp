// main.cpp -- device app -- Ward Information Integrator (ICU). Constructs each
// uplink message the integrator forwards to the Hospital Management System and
// prints it as JSON. The integrator also caches downlink reference data (the
// pull messages: common.harpia types + prescription_cache); wire the generated
// CRUDL DAO / REST bindings for those the way HarpiaTest/app_example/consumer does.
//
// This project is Fixed infrastructure, not a Human Interaction Device, so
// there is no human_mock -- a realistic inbound feed is the aggregate of the
// ICU devices' own human_mock streams.
//
// Consumes harpia-generated code as a black box. Generate a project from this
// folder first (see README.md); CMake writes harpia_generated_includes.h into
// the build tree from the generated message headers (protofiles/*.pb.h), so no
// md5 hash needs to be spelled out here.
#include "harpia_generated_includes.h"

#include <iostream>
#include <string>

#include <google/protobuf/util/json_util.h>

int main() {
    ::google::protobuf::util::JsonPrintOptions jopts;
    auto dump = [&](const char* label, const ::google::protobuf::Message& m) {
        std::string js;
        (void) ::google::protobuf::util::MessageToJsonString(m, &js, jopts);
        std::cout << label << ": " << js << std::endl;
    };

    const std::string ward_id = "ICU";

    {
        ::ward_telemetry_batch m;
        m.set_ward_id(ward_id);
        m.set_device_id("MON-2201");
        m.set_metric_name("heart_rate_bpm");
        m.set_metric_value(78.0f);
        m.set_sample_epoch_millis(1756142400);
        dump("ward_telemetry_batch", m);
    }
    {
        ::ward_alarm_relay m;
        m.set_ward_id(ward_id);
        m.set_device_id("VENT-1102");
        m.set_alarm_code(412);
        m.set_active(1);
        dump("ward_alarm_relay", m);
    }
    {
        ::ward_audit_relay m;
        m.set_source_id("PUMP-1180");
        m.set_category("selftest");
        m.set_detail("occlusion sensor pass");
        m.set_epoch_millis(1756142401);
        dump("ward_audit_relay", m);
    }
    {
        ::store_forward_replay m;
        m.set_ward_id(ward_id);
        m.set_first_epoch_millis(1756142000);
        m.set_last_epoch_millis(1756142400);
        m.set_record_count(1284);
        dump("store_forward_replay", m);
    }
    {
        ::integrator_link_status m;
        m.set_ward_id(ward_id);
        m.set_buffered_records(0);
        dump("integrator_link_status", m);
    }

    std::cout << "Ward Information Integrator (ICU) device app: done" << std::endl;
    return 0;
}
