# Hospital Point of Information

Worked harpia example project for the **Hospital Point of Information** from
[`../../Projects.md`](../../Projects.md) (section 0 and the Connectivity Map at
the end). See
[`hospital-point-of-information.md`](./hospital-point-of-information.md) for the
verbatim blueprint entry.

## Role

A wall-mounted display panel. It connects to its local **Ward Information
Integrator**: it pulls the data it shows (room / bed assignment, care team,
precaution flags, announcements) and pushes back interaction events (touch
logs, nurse-call, alert acknowledgements, heartbeat). It is **Fixed
infrastructure** — not a Human Interaction Device in the blueprint sense (the
touch screen faces visitors and staff, not the patient) — so it is a C++ /
CMake project with a single `device_app` target and **no `human_mock`**.

## What is here

| File | Role |
|---|---|
| [`hospital-point-of-information.md`](./hospital-point-of-information.md) | the blueprint lines for this component |
| [`hospital_point_of_information.harpia`](./hospital_point_of_information.harpia) | outbound interaction (`touch_interaction`, `assistance_request`, `alert_acknowledgement`, `panel_heartbeat`) as `push`; displayed data (`room_assignment`, `precaution_flags`, `ward_announcement`) as `pull` |
| `Include/common.harpia` | shared inbound types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) |
| build infra | `CMakeLists.txt` + `vcpkg.json` (C++/CMake) |
| device code | `src/main.cpp` (builds each outbound message, prints it as JSON) |

## Generate + build + run

```sh
# 1. generate the C++ target
bash ./run_harpia.sh TestProjects/0-hospital-management-and-information/hospital-point-of-information TestProjects/_gen/hospital-point-of-information --no-build

# 2. build inside the toolchain image (-DHARPIA_GEN must be ABSOLUTE)
bash docker/run.sh bash -c '
  cmake -S TestProjects/0-hospital-management-and-information/hospital-point-of-information -B TestProjects/0-hospital-management-and-information/hospital-point-of-information/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/hospital-point-of-information &&
  cmake --build TestProjects/0-hospital-management-and-information/hospital-point-of-information/_build -j"$(nproc)"'

# 3. run (inside the image)
bash docker/run.sh bash -c './TestProjects/0-hospital-management-and-information/hospital-point-of-information/_build/device_app'
```

Clean up with `rm -rf TestProjects/_gen/hospital-point-of-information TestProjects/0-hospital-management-and-information/hospital-point-of-information/_build`.

## Notes

- Generated identifiers are **md5-hash-qualified** off the `.harpia` input; the
  `CMakeLists.txt` globs the generated headers into
  `harpia_generated_includes.h` so this folder never hard-codes a hash.
- See [`../../../examples/consumer`](../../../examples/consumer) for wiring the
  CRUDL DAO, REST bindings, gRPC service or ZMQ transport.
