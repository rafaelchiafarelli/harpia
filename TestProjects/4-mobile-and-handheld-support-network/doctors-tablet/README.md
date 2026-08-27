# Doctor's Tablet
*   **Main Features:** A mobile computer screen allowing medical staff to view live patient data from anywhere in the building.
*   **📡 Network Outbound:** Clinician interaction input logs, explicit authorization token requests.
*   **📥 Network Inbound:** Live streaming waveform graphs (ECG), real-time alarm feeds, and complete historical patient charts.
*   **Mobile device**

## What is here

| File | Role |
|---|---|
| [`doctors_tablet.harpia`](./doctors_tablet.harpia) | the assembled `.harpia` schema (messages `clinician_interaction_log`, `authorization_request`, plus inbound types from `Include/common.harpia`) |
| `Include/common.harpia` | shared inbound types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) |
| build infra | `settings.gradle` + `build.gradle` + `gradle.properties` (Android app module, AGP 8.2.2, modelled on `HarpiaTest/app_example/android_consumer`) |
| device code | `src/main/java/com/harpia/doctorstablet/DeviceApp.java` |

## Schema

The Network Outbound data becomes `push` / `stream` / `event` messages (the
device is the source); Network Inbound data becomes `pull` messages. Anything
that is a record gets a table name and so generates DB/CRUDL/REST/SOAP; pure
control packets stay table-less.

- Not marked as a Human Interaction Device, so there is **no human-mock** -- `DeviceApp` is purely a consumer of the inbound streams.

## Generate + build + run

Run everything through `Docker/run.sh` (it builds/uses the `harpia-build`
image, which carries the JDK + Gradle + Android SDK).

```sh
# 1. generate a Java-target project from this folder, then build its jar
Docker/run.sh bash -c '
  HARPIA_GEN_LANG=java \
    HARPIA_INPUT_FILE=TestProjects/4-mobile-and-handheld-support-network/doctors-tablet/doctors_tablet.harpia \
    HARPIA_INCLUDE_FOLDER=TestProjects/4-mobile-and-handheld-support-network/doctors-tablet/Include \
    HARPIA_OUTPUT_DIR=/tmp/doctors-tablet_gen python3 main.py &&
  (cd /tmp/doctors-tablet_gen/java && gradle --no-daemon build)'

# 2. assemble this consumer module against the generated jar
Docker/run.sh bash -c '
  cd TestProjects/4-mobile-and-handheld-support-network/doctors-tablet &&
  gradle --no-daemon -PharpiaGenDir=/tmp/doctors-tablet_gen assembleDebug'
```

`run_harpia.sh` is the C++-target helper only; the Java target is driven by
`main.py` with `HARPIA_GEN_LANG=java` (wrapped in `Docker/run.sh` above).
Entry points, pure Java so a desktop JVM is enough:
`com.harpia.doctorstablet.DeviceApp`.

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
