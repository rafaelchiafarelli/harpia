// main.cpp -- device app -- Hospital Management System. Constructs each
// outbound (published) message the HMS broadcasts to its clients and prints it
// as JSON. The HMS also ingests ward data (the pull messages in the schema);
// wire the generated CRUDL DAO / REST bindings for those the way
// HarpiaTest/app_example/consumer does.
//
// This project is the central backend, not a Human Interaction Device, so
// there is no human_mock.
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

    {
        ::adt_status_update m;
        m.set_patient_id("PID-00042");
        m.set_encounter_id("ENC-1007");
        m.set_status("admitted");
        m.set_bed_assignment("ICU-03");
        dump("adt_status_update", m);
    }
    {
        ::prescription_release m;
        m.set_prescription_id("RX-5521");
        m.set_patient_id("PID-00042");
        m.set_drug_name("Norepinephrine");
        m.set_dose_rate_ml_h(20.0f);
        m.set_ordering_physician("dr.tanaka");
        dump("prescription_release", m);
    }
    {
        ::nutrition_plan_release m;
        m.set_patient_id("PID-00042");
        m.set_target_rate_ml_h(55.0f);
        m.set_total_target_ml(1320);
        dump("nutrition_plan_release", m);
    }
    {
        ::authorization_token m;
        m.set_login_id("dr.tanaka");
        m.set_token("tok-9f3a2b");
        m.set_expires_epoch_millis(1893456);
        dump("authorization_token", m);
    }
    {
        ::device_bed_assignment m;
        m.set_device_id("PUMP-1180");
        m.set_bed_assignment("ICU-03");
        m.set_ward_id("ICU");
        dump("device_bed_assignment", m);
    }
    {
        ::facility_clock_tick m;
        m.set_epoch_millis(1756142400);
        m.set_timezone_offset_minutes(-180);
        dump("facility_clock_tick", m);
    }

    std::cout << "Hospital Management System device app: done" << std::endl;
    return 0;
}
