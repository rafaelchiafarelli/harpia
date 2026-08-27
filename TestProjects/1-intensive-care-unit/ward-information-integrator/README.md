# Ward Information Integrator — ICU
*   **Main Features:** Ward-local edge server that aggregates every ICU device onto one fabric. Runs as a local publish/subscribe broker so bedside events (alarms, live vitals, ICP threshold breaches) reach other ICU endpoints in real time, and as a store-and-forward gateway that relays the same data up to the HMS. Caches HMS reference data (demographics, orders, care-team, clock) locally so the ICU keeps functioning through an HMS or WAN outage, and serves as the ward's local clock stratum.
*   **📡 Network Outbound:** Aggregated ICU telemetry and alarm streams, per-device health and audit logs, and store-and-forward replay batches — all to the HMS.
*   **📥 Network Inbound:** Patient demographics, electronic prescriptions, ADT status, clinician identity, device-to-bed assignments, and clock sync — from the HMS, for local redistribution to ICU devices.
*   **🔀 Ward Information Integrator**
*   **Fixed infrastructure** (Rack- or wall-mounted ward server, redundant pair recommended; no patient contact, not mobile).

## Role

This is not a bedside device — it is the ICU's **edge hub**. Every ICU device
connects only to this node; the integrator brokers ward-internal traffic in
real time and relays everything up to the Hospital Management System
([`../../0-hospital-management-and-information/hospital-management-system/`](../../0-hospital-management-and-information/hospital-management-system/)).
It is **Fixed infrastructure**, so it is a C++ / CMake project with a single
`device_app` target and **no `human_mock`** (a realistic inbound feed is the
sum of the ICU devices' own human-mock streams).

## What is here

| File | Role |
|---|---|
| [`ward_information_integrator.harpia`](./ward_information_integrator.harpia) | the assembled schema: uplink messages to the HMS (`ward_telemetry_batch`, `ward_alarm_relay`, `ward_audit_relay`, `store_forward_replay`, `integrator_link_status`) as `push`; cached downlink data (`prescription_cache` + the `common.harpia` types) as `pull` |
| `Include/common.harpia` | shared inbound types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) — here they model the HMS reference data the integrator caches for redistribution |
| build infra | `CMakeLists.txt` + `vcpkg.json` (C++/CMake, modelled on `HarpiaTest/app_example/consumer`) |
| device code | `src/main.cpp` (builds each uplink message, prints it as JSON) |

## Schema

Uplink data the integrator sends to the HMS becomes `push` / `stream` / `event`
messages (the integrator is the source); downlink data it receives and caches
becomes `pull` messages. Records get a table name and so generate
DB/CRUDL/REST/SOAP; pure control packets stay table-less.

## Generate + build + run

```sh
# 1. generate the C++ target (helper script; --no-build = codegen only)
./run_harpia.sh TestProjects/1-intensive-care-unit/ward-information-integrator TestProjects/_gen/ward-information-integrator-icu --no-build

# 2. build this consumer inside the toolchain image.
#    NOTE -DHARPIA_GEN must be ABSOLUTE; the repo is /harpia inside the image.
bash Docker/run.sh bash -c '
  cmake -S TestProjects/1-intensive-care-unit/ward-information-integrator -B TestProjects/1-intensive-care-unit/ward-information-integrator/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/ward-information-integrator-icu &&
  cmake --build TestProjects/1-intensive-care-unit/ward-information-integrator/_build -j"$(nproc)"'

# 3. run the executable (inside the image)
bash Docker/run.sh bash -c './TestProjects/1-intensive-care-unit/ward-information-integrator/_build/device_app'
```

`device_app` builds one of each uplink message and prints it as JSON. Clean up
with `rm -rf TestProjects/_gen/ward-information-integrator-icu TestProjects/1-intensive-care-unit/ward-information-integrator/_build`.

## Notes

- Generated identifiers are **md5-hash-qualified** off the `.harpia` input; the
  C++ `CMakeLists.txt` globs the generated headers into
  `harpia_generated_includes.h` so this folder never hard-codes a hash.
- This project only exercises the message-class + JSON surface. See
  [`../../../HarpiaTest/app_example/consumer`](../../../HarpiaTest/app_example/consumer) for wiring the CRUDL
  DAO, REST bindings, gRPC service or ZMQ transport (the integrator's real
  uplink and cache).
