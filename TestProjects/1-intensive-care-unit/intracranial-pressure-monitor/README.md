# Intracranial Pressure (ICP) Monitor
*   **Main Features:** Measures the fluid pressure levels inside the cranium to prevent brain injury.
*   **📡 Network Outbound:** Continuous Mean ICP values (mmHg), pressure waveform trends, and high-pressure boundary threshold alerts.
*   **📥 Network Inbound:** Zero-calibration baseline confirmations.
*   **⚠️ Human Interaction Device** (Connects directly via a pressure sensor catheter surgically placed inside the skull).
*   **Mobile device**

## What is here

| File | Role |
|---|---|
| [`icp_monitor.harpia`](./icp_monitor.harpia) | the assembled `.harpia` schema (messages `icp_reading`, `icp_threshold_alert`, plus inbound types from `Include/common.harpia`) |
| `Include/common.harpia` | shared inbound types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) |
| build infra | `settings.gradle` + `build.gradle` + `gradle.properties` (Android app module, AGP 8.2.2, modelled on `HarpiaTest/app_example/android_consumer`) |
| device code | `src/main/java/com/harpia/icpmonitor/DeviceApp.java`, `.../HumanMock.java` |

## Schema

The Network Outbound data becomes `push` / `stream` / `event` messages (the
device is the source); Network Inbound data becomes `pull` messages. Anything
that is a record gets a table name and so generates DB/CRUDL/REST/SOAP; pure
control packets stay table-less.

- **Human Interaction Device** -> ships a **human-mock**: a standalone runnable that models the physiological signal source and normal operator
  actions for this device (baseline + bounded noise, slow trends, low-probability boundary events) and emits them as the generated message
  types, so it is a drop-in traffic generator for `device_app`.

## Generate + build + run

Run everything through `Docker/run.sh` (it builds/uses the `harpia-build`
image, which carries the JDK + Gradle + Android SDK).

```sh
# 1. generate a Java-target project from this folder, then build its jar
Docker/run.sh bash -c '
  HARPIA_GEN_LANG=java \
    HARPIA_INPUT_FILE=TestProjects/1-intensive-care-unit/intracranial-pressure-monitor/icp_monitor.harpia \
    HARPIA_INCLUDE_FOLDER=TestProjects/1-intensive-care-unit/intracranial-pressure-monitor/Include \
    HARPIA_OUTPUT_DIR=/tmp/intracranial-pressure-monitor_gen python3 main.py &&
  (cd /tmp/intracranial-pressure-monitor_gen/java && gradle --no-daemon build)'

# 2. assemble this consumer module against the generated jar
Docker/run.sh bash -c '
  cd TestProjects/1-intensive-care-unit/intracranial-pressure-monitor &&
  gradle --no-daemon -PharpiaGenDir=/tmp/intracranial-pressure-monitor_gen assembleDebug'
```

`run_harpia.sh` is the C++-target helper only; the Java target is driven by
`main.py` with `HARPIA_GEN_LANG=java` (wrapped in `Docker/run.sh` above).
Entry points, pure Java so a desktop JVM is enough:
`com.harpia.icpmonitor.DeviceApp`, `com.harpia.icpmonitor.HumanMock`.

## Notes

- Generated identifiers are **md5-hash-qualified** off the `.harpia` input
  (`<msg>_<hash>_crudl.h`, accessor `id_<hash>()`); regenerate from your own
  edits and the hash moves with them. The C++ `CMakeLists.txt` globs the
  generated headers so this folder never hard-codes a hash.
- This project only exercises the message-class + JSON surface. The C++ code
  serialises with protobuf's own `MessageToJsonString` so one program can touch
  several message types; the generated `json/<msg>_<hash>_json.h` convenience
  adapter (`harpia::json::to_json`) is one-message-per-translation-unit by
  design -- see [`../../../HarpiaTest/app_example/consumer`](../../../HarpiaTest/app_example/consumer) for
  that form, and for wiring the CRUDL DAO, REST bindings, gRPC service or ZMQ
  transport. The Java side does the same via
  [`../../../HarpiaTest/app_example/android_consumer`](../../../HarpiaTest/app_example/android_consumer).
