# Ward Information Integrator — OR
*   **Main Features:** Theatre-local edge server that aggregates every OR device onto one fabric. Brokers intra-theatre traffic (case events, gas/flow alarms, calibration status) in real time and relays it up to the HMS. Caches the pre-surgical checklist, case validation records and surgeon identities locally so a running case is unaffected by an HMS or WAN outage, and holds the theatre's local clock stratum for procedural timestamp markers. High-bandwidth video (robot console, endoscopy tower) is routed on a separate in-theatre A/V path and is not carried on this data fabric.
*   **📡 Network Outbound:** Aggregated OR telemetry and alarm streams, per-device calibration and audit logs, and store-and-forward replay batches — all to the HMS.
*   **📥 Network Inbound:** Pre-surgical checklists, active case validation records, surgeon login profiles, patient ID assignment tags, and procedural timestamp sync — from the HMS, for local redistribution to OR devices.
*   **🔀 Ward Information Integrator**
*   **Fixed infrastructure** (Rack-mounted theatre server, redundant pair recommended; no patient contact, not mobile).


## Role

Not a theatre device — the OR's **edge hub**. Every OR device connects only to
this node; it brokers intra-theatre traffic in real time and relays everything
up to the Hospital Management System
([`../../0-hospital-management-and-information/hospital-management-system/`](../../0-hospital-management-and-information/hospital-management-system/)).
It is **Fixed infrastructure**, so it is a C++ / CMake project with a single
`device_app` target and **no `human_mock`**. High-bandwidth surgical video is
carried on a separate in-theatre A/V path, not on this data fabric.

## What is here

| File | Role |
|---|---|
| [`ward_information_integrator.harpia`](./ward_information_integrator.harpia) | uplink messages to the HMS (`ward_telemetry_batch`, `ward_alarm_relay`, `ward_audit_relay`, `store_forward_replay`, `integrator_link_status`) as `push`; cached downlink data (`case_validation_cache` + the `common.harpia` types) as `pull` |
| `Include/common.harpia` | shared inbound types — here they model the HMS reference data the hub caches for redistribution |
| build infra | `CMakeLists.txt` + `vcpkg.json` (C++/CMake) |
| device code | `src/main.cpp` (builds each uplink message, prints it as JSON) |

## Generate + build + run

```sh
# 1. generate the C++ target
./run_harpia.sh TestProjects/2-operating-room/ward-information-integrator TestProjects/_gen/ward-information-integrator-or --no-build

# 2. build inside the toolchain image (-DHARPIA_GEN must be ABSOLUTE)
bash docker/run.sh bash -c '
  cmake -S TestProjects/2-operating-room/ward-information-integrator -B TestProjects/2-operating-room/ward-information-integrator/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/ward-information-integrator-or &&
  cmake --build TestProjects/2-operating-room/ward-information-integrator/_build -j"$(nproc)"'

# 3. run (inside the image)
bash docker/run.sh bash -c './TestProjects/2-operating-room/ward-information-integrator/_build/device_app'
```

Clean up with `rm -rf TestProjects/_gen/ward-information-integrator-or TestProjects/2-operating-room/ward-information-integrator/_build`.

## Notes

- Generated identifiers are **md5-hash-qualified** off the `.harpia` input; the
  `CMakeLists.txt` globs the generated headers into
  `harpia_generated_includes.h` so this folder never hard-codes a hash.
- See [`../../../HarpiaTest/app_example/consumer`](../../../HarpiaTest/app_example/consumer) for wiring the
  CRUDL DAO, REST bindings, gRPC service or ZMQ transport.
