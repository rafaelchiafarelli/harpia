# Anesthesia Machine

Worked harpia example project for the **Anesthesia Machine** from
[`../../Projects.md`](../../Projects.md). See [`anesthesia-machine.md`](./anesthesia-machine.md) for the
verbatim blueprint entry.

## What is here

| File | Role |
|---|---|
| [`anesthesia-machine.md`](./anesthesia-machine.md) | the blueprint lines for this device |
| [`anesthesia.harpia`](./anesthesia.harpia) | the assembled `.harpia` schema (messages `agent_delivery`, `agent_depletion_warning`, `ventilation_loop`, plus inbound types from `Include/common.harpia`) |
| `Include/common.harpia` | shared inbound types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) |
| build infra | `settings.gradle` + `build.gradle` + `gradle.properties` (Android app module, AGP 8.2.2, modelled on `examples/android_consumer`) |
| device code | `src/main/java/com/harpia/anesthesia/DeviceApp.java`, `.../HumanMock.java` |

## Schema

The Network Outbound data becomes `push` / `stream` / `event` messages (the
device is the source); Network Inbound data becomes `pull` messages. Anything
that is a record gets a table name and so generates DB/CRUDL/REST/SOAP; pure
control packets stay table-less.

- **Human Interaction Device** -> ships a **human-mock**: a standalone runnable that models the physiological signal source and normal operator
  actions for this device (baseline + bounded noise, slow trends, low-probability boundary events) and emits them as the generated message
  types, so it is a drop-in traffic generator for `device_app`.

## Generate + build + run

Run everything through `docker/run.sh` (it builds/uses the `harpia-build`
image, which carries the JDK + Gradle + Android SDK).

```sh
# 1. generate a Java-target project from this folder, then build its jar
docker/run.sh bash -c '
  HARPIA_GEN_LANG=java \
    HARPIA_INPUT_FILE=TestProjects/2-operating-room/anesthesia-machine/anesthesia.harpia \
    HARPIA_INCLUDE_FOLDER=TestProjects/2-operating-room/anesthesia-machine/Include \
    HARPIA_OUTPUT_DIR=/tmp/anesthesia-machine_gen python3 main.py &&
  (cd /tmp/anesthesia-machine_gen/java && gradle --no-daemon build)'

# 2. assemble this consumer module against the generated jar
docker/run.sh bash -c '
  cd TestProjects/2-operating-room/anesthesia-machine &&
  gradle --no-daemon -PharpiaGenDir=/tmp/anesthesia-machine_gen assembleDebug'
```

`run_harpia.sh` is the C++-target helper only; the Java target is driven by
`main.py` with `HARPIA_GEN_LANG=java` (wrapped in `docker/run.sh` above).
Entry points, pure Java so a desktop JVM is enough:
`com.harpia.anesthesia.DeviceApp`, `com.harpia.anesthesia.HumanMock`.

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
