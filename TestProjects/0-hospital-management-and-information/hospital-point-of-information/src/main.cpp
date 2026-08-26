// main.cpp -- device app -- Hospital Point of Information. Constructs each
// outbound message the panel emits (visitor / staff interaction) and prints it
// as JSON. The panel also pulls the data it displays (room_assignment,
// precaution_flags, ward_announcement); wire the generated CRUDL DAO / REST
// bindings for those the way examples/consumer does.
//
// This project is Fixed infrastructure (a visitor-facing panel, not a Human
// Interaction Device that touches the patient), so there is no human_mock.
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

    const std::string panel_id = "POI-W3-07";

    {
        ::touch_interaction m;
        m.set_panel_id(panel_id);
        m.set_screen_id("room-status");
        m.set_epoch_millis(1756142400);
        dump("touch_interaction", m);
    }
    {
        ::assistance_request m;
        m.set_panel_id(panel_id);
        m.set_room_id("W3-214");
        dump("assistance_request", m);
    }
    {
        ::alert_acknowledgement m;
        m.set_panel_id(panel_id);
        m.set_alert_id(88123);
        m.set_acknowledged_by("nurse.lima");
        dump("alert_acknowledgement", m);
    }
    {
        ::panel_heartbeat m;
        m.set_panel_id(panel_id);
        m.set_uptime_seconds(864000);
        m.set_display_ok(1);
        dump("panel_heartbeat", m);
    }

    std::cout << "Hospital Point of Information device app: done" << std::endl;
    return 0;
}
