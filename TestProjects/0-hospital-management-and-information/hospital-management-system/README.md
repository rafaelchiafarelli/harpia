# Hospital Management System (HMS)
*   **Main Features:** Central facility backend that owns the master patient record, the admit / discharge / transfer workflow, medication and nutrition orders, the staff directory, and the authoritative facility clock. Every clinical device on the network is a client of this system: it is the source of nearly all **📥 Network Inbound** data the devices receive, and the sink for nearly all their **📡 Network Outbound** data.
*   **📡 Network Outbound:** Patient demographic profiles, admit/discharge/transfer status updates, verified electronic prescriptions and daily nutrition plans, clinician login profiles and authorization tokens, clock synchronization packets, and device-to-bed location assignments.
*   **📥 Network Inbound:** Live vital-sign metrics and numerical alarms from bedside devices, infusion and feeding delivery totals, captured surgical snapshots, device self-test and calibration status, and event / audit logs from every connected unit.
*   **Fixed infrastructure** (Rack-mounted server; no direct patient contact, not a mobile deployment).

## Role

The **central backend** every other project connects to (via its Ward
Information Integrator). It publishes reference data down to the wards
(demographics, orders, ADT, clinician identity, clock, device-to-bed map) and
ingests aggregated telemetry, alarms and audit logs back up from each ward
integrator. It is **Fixed infrastructure**, so it is a C++ / CMake project with
a single `device_app` target and **no `human_mock`**.

## What is here

| File | Role |
|---|---|
| [`hospital_management_system.harpia`](./hospital_management_system.harpia) | published reference data (`adt_status_update`, `prescription_release`, `nutrition_plan_release`, `authorization_token`, `device_bed_assignment`, `facility_clock_tick`) as `push`; ward data it ingests (`ward_telemetry_ingest`, `ward_alarm_ingest`, `device_selftest_ingest`, `audit_log_ingest`) as `pull` |
| `Include/common.harpia` | shared client identity / location types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) |
| build infra | `CMakeLists.txt` + `vcpkg.json` (C++/CMake) |
| device code | `src/main.cpp` (builds each published message, prints it as JSON) |

## Schema

Data the HMS publishes to its clients becomes `push` / `event` messages (the
HMS is the source); data it collects back from the wards becomes `pull`
messages. Records get a table name and so generate DB/CRUDL/REST/SOAP.

## Generate + build + run

```sh
# 1. generate the C++ target
./run_harpia.sh TestProjects/0-hospital-management-and-information/hospital-management-system TestProjects/_gen/hospital-management-system --no-build

# 2. build inside the toolchain image (-DHARPIA_GEN must be ABSOLUTE)
bash Docker/run.sh bash -c '
  cmake -S TestProjects/0-hospital-management-and-information/hospital-management-system -B TestProjects/0-hospital-management-and-information/hospital-management-system/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/hospital-management-system &&
  cmake --build TestProjects/0-hospital-management-and-information/hospital-management-system/_build -j"$(nproc)"'

# 3. run (inside the image)
bash Docker/run.sh bash -c './TestProjects/0-hospital-management-and-information/hospital-management-system/_build/device_app'
```

Clean up with `rm -rf TestProjects/_gen/hospital-management-system TestProjects/0-hospital-management-and-information/hospital-management-system/_build`.

## Notes

- Generated identifiers are **md5-hash-qualified** off the `.harpia` input; the
  `CMakeLists.txt` globs the generated headers into
  `harpia_generated_includes.h` so this folder never hard-codes a hash.
- See [`../../../HarpiaTest/app_example/consumer`](../../../HarpiaTest/app_example/consumer) for wiring the
  CRUDL DAO, REST bindings, gRPC service or ZMQ transport (the HMS's real
  north/south interfaces).
