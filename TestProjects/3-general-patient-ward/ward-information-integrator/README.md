# Ward Information Integrator — General Patient Ward

Worked harpia example project for the **Ward Information Integrator** of the
General Patient Ward, from [`../../Projects.md`](../../Projects.md) (section 3
and the Connectivity Map at the end). See
[`ward-information-integrator.md`](./ward-information-integrator.md) for the
verbatim blueprint entry.

## Role

Not a bedside device — the ward's **edge hub**. Every general-ward device
connects only to this node; it brokers ward-internal events (bed-exit, SCD/feed
alarms, scan completions) to the nurses' station and Points of Information in
real time, and relays everything up to the Hospital Management System
([`../../0-hospital-management-and-information/hospital-management-system/`](../../0-hospital-management-and-information/hospital-management-system/)).
It is **Fixed infrastructure**, so it is a C++ / CMake project with a single
`device_app` target and **no `human_mock`**.

## What is here

| File | Role |
|---|---|
| [`ward-information-integrator.md`](./ward-information-integrator.md) | the blueprint lines for this component |
| [`ward_information_integrator.harpia`](./ward_information_integrator.harpia) | uplink messages to the HMS (`ward_telemetry_batch`, `ward_alarm_relay`, `ward_audit_relay`, `store_forward_replay`, `integrator_link_status`) as `push`; cached downlink data (`nutrition_plan_cache` + the `common.harpia` types) as `pull` |
| `Include/common.harpia` | shared inbound types — here they model the HMS reference data the hub caches for redistribution |
| build infra | `CMakeLists.txt` + `vcpkg.json` (C++/CMake) |
| device code | `src/main.cpp` (builds each uplink message, prints it as JSON) |

## Generate + build + run

```sh
# 1. generate the C++ target
bash ./run_harpia.sh TestProjects/3-general-patient-ward/ward-information-integrator TestProjects/_gen/ward-information-integrator-ward3 --no-build

# 2. build inside the toolchain image (-DHARPIA_GEN must be ABSOLUTE)
bash docker/run.sh bash -c '
  cmake -S TestProjects/3-general-patient-ward/ward-information-integrator -B TestProjects/3-general-patient-ward/ward-information-integrator/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/ward-information-integrator-ward3 &&
  cmake --build TestProjects/3-general-patient-ward/ward-information-integrator/_build -j"$(nproc)"'

# 3. run (inside the image)
bash docker/run.sh bash -c './TestProjects/3-general-patient-ward/ward-information-integrator/_build/device_app'
```

Clean up with `rm -rf TestProjects/_gen/ward-information-integrator-ward3 TestProjects/3-general-patient-ward/ward-information-integrator/_build`.

## Notes

- Generated identifiers are **md5-hash-qualified** off the `.harpia` input; the
  `CMakeLists.txt` globs the generated headers into
  `harpia_generated_includes.h` so this folder never hard-codes a hash.
- See [`../../../examples/consumer`](../../../examples/consumer) for wiring the
  CRUDL DAO, REST bindings, gRPC service or ZMQ transport.
