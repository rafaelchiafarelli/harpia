# Heart-Lung Machine
*   **Main Features:** Temporarily bypasses and takes over the physical pumping and oxygenation work of the heart and lungs during open surgery.
*   **📡 Network Outbound:** Extracorporeal Blood Flow Rate (L/min), Blood Temperature (°C), Oxygenation levels, and system safety pressures.
*   **📥 Network Inbound:** Surgical procedural timestamp markers.
*   **⚠️ Human Interaction Device** (Connects directly via large plastic tubes inserted into the patient’s primary blood vessels).


## What is here

| File | Role |
|---|---|
| [`heart_lung.harpia`](./heart_lung.harpia) | the assembled `.harpia` schema (messages `perfusion_metrics`, `perfusion_safety_alarm`, plus inbound types from `Include/common.harpia`) |
| `Include/common.harpia` | shared inbound types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) |
| build infra | `CMakeLists.txt` + `vcpkg.json` (C++/CMake, modelled on `examples/consumer`) |
| device code | `src/main.cpp` (device app), `src/human_mock.cpp` (human-mock) |

## Schema

The Network Outbound data becomes `push` / `stream` / `event` messages (the
device is the source); Network Inbound data becomes `pull` messages. Anything
that is a record gets a table name and so generates DB/CRUDL/REST/SOAP; pure
control packets stay table-less.

- **Human Interaction Device** -> ships a **human-mock**: a standalone runnable that models the physiological signal source and normal operator
  actions for this device (baseline + bounded noise, slow trends, low-probability boundary events) and emits them as the generated message
  types, so it is a drop-in traffic generator for `device_app`.

## Generate + build + run

Three helper-script steps. Step 1 generates the harpia project **into the repo
tree** (`TestProjects/_gen/heart-lung-machine/`, gitignored) so the build container -- which only mounts the
repo -- can see it. The built binaries link against the image's protobuf, so
they only run **inside the image** (`./device_app` on the host fails with
`libprotobuf.so.32: cannot open shared object file`).

```sh
# 1. generate the C++ target (helper script; --no-build = codegen only,
#    do NOT run the generated ctest suite, it is slow)
./run_harpia.sh TestProjects/2-operating-room/heart-lung-machine TestProjects/_gen/heart-lung-machine --no-build

# 2. build this consumer inside the toolchain image.
#    NOTE -DHARPIA_GEN must be ABSOLUTE; the repo is /harpia inside the image.
bash docker/run.sh bash -c '
  cmake -S TestProjects/2-operating-room/heart-lung-machine -B TestProjects/2-operating-room/heart-lung-machine/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/heart-lung-machine &&
  cmake --build TestProjects/2-operating-room/heart-lung-machine/_build -j"$(nproc)"'

# 3. run the executables (inside the image)
bash docker/run.sh bash -c './TestProjects/2-operating-room/heart-lung-machine/_build/device_app
  ./TestProjects/2-operating-room/heart-lung-machine/_build/human_mock | head'
```

`device_app` builds one of each outbound message and prints it as JSON;
`human_mock` streams 20 ticks of simulated human/patient traffic.
Clean up with `rm -rf TestProjects/_gen/heart-lung-machine TestProjects/2-operating-room/heart-lung-machine/_build`.

## Notes

- Generated identifiers are **md5-hash-qualified** off the `.harpia` input
  (`<msg>_<hash>_crudl.h`, accessor `id_<hash>()`); regenerate from your own
  edits and the hash moves with them. The C++ `CMakeLists.txt` globs the
  generated headers so this folder never hard-codes a hash.
- This project only exercises the message-class + JSON surface. The C++ code
  serialises with protobuf's own `MessageToJsonString` so one program can touch
  several message types; the generated `json/<msg>_<hash>_json.h` convenience
  adapter (`harpia::json::to_json`) is one-message-per-translation-unit by
  design -- see [`../../../examples/consumer`](../../../examples/consumer) for
  that form, and for wiring the CRUDL DAO, REST bindings, gRPC service or ZMQ
  transport. The Java side does the same via
  [`../../../examples/android_consumer`](../../../examples/android_consumer).
