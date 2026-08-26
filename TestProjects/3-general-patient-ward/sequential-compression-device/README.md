# Sequential Compression Device (SCD)
*   **Main Features:** Uses air pumps to sequentially inflate sleeves wrapped around legs to force blood flow and prevent clots.
*   **📡 Network Outbound:** Inflatable sleeve pressure cycles (mmHg), operation timer logs, and sleeve-disconnected alerts.
*   **📥 Network Inbound:** Simple device location update pings.
*   **⚠️ Human Interaction Device** (Inflatable multi-chamber compression sleeves are wrapped tightly around the patient's legs).

## What is here

| File | Role |
|---|---|
| [`scd.harpia`](./scd.harpia) | the assembled `.harpia` schema (messages `compression_cycle`, `scd_runtime_log`, `sleeve_disconnected_alert`, plus inbound types from `Include/common.harpia`) |
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
tree** (`TestProjects/_gen/sequential-compression-device/`, gitignored) so the build container -- which only mounts the
repo -- can see it. The built binaries link against the image's protobuf, so
they only run **inside the image** (`./device_app` on the host fails with
`libprotobuf.so.32: cannot open shared object file`).

```sh
# 1. generate the C++ target (helper script; --no-build = codegen only,
#    do NOT run the generated ctest suite, it is slow)
./run_harpia.sh TestProjects/3-general-patient-ward/sequential-compression-device TestProjects/_gen/sequential-compression-device --no-build

# 2. build this consumer inside the toolchain image.
#    NOTE -DHARPIA_GEN must be ABSOLUTE; the repo is /harpia inside the image.
bash docker/run.sh bash -c '
  cmake -S TestProjects/3-general-patient-ward/sequential-compression-device -B TestProjects/3-general-patient-ward/sequential-compression-device/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/sequential-compression-device &&
  cmake --build TestProjects/3-general-patient-ward/sequential-compression-device/_build -j"$(nproc)"'

# 3. run the executables (inside the image)
bash docker/run.sh bash -c './TestProjects/3-general-patient-ward/sequential-compression-device/_build/device_app
  ./TestProjects/3-general-patient-ward/sequential-compression-device/_build/human_mock | head'
```

`device_app` builds one of each outbound message and prints it as JSON;
`human_mock` streams 20 ticks of simulated human/patient traffic.
Clean up with `rm -rf TestProjects/_gen/sequential-compression-device TestProjects/3-general-patient-ward/sequential-compression-device/_build`.

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
