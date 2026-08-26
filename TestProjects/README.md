# TestProjects -- worked harpia example projects

This folder turns the **Hospital Electronic Equipment & Network Data Blueprint**
([`Projects.md`](./Projects.md)) into 20 small, self-contained example projects:
one per medical device (15), plus the 5 facility-infrastructure components —
the Hospital Management System, the Hospital Point of Information, and one Ward
Information Integrator per clinical ward — grouped by clinical environment
(sections 0–4 of the blueprint).
Each project *creates and consumes* harpia-generated code, the same way
[`../examples/consumer`](../examples/consumer) and
[`../examples/android_consumer`](../examples/android_consumer) do -- it is
reference material, not wired into `main.py` or the test suite.

## Layout

```
TestProjects/
  _shared/common.harpia        shared inbound message types (copied into each project's Include/)
  <n>-<room>/                  one folder per numbered room in Projects.md
    <device>/                  one folder per device
      <device>.md              the verbatim blueprint lines for that device
      <name>.harpia            assembled schema: Outbound -> push/stream/event, Inbound -> pull
      Include/common.harpia    copy of _shared/common.harpia
      src/                     device code (see per-language note below)
      README.md                generate + build + run for that project
      + build infra            CMake/vcpkg (C++) or Gradle Android module (Java)
```

## Rules used to derive each project

| Blueprint marker | Consequence |
|---|---|
| **Mobile device** | Java target -- single-module **Android app module** (Gradle, AGP 8.2.2), sources under `src/main/java`. |
| *(not Mobile device)* | C++ target -- **CMake + vcpkg** project, sources under `src/`. |
| **Human Interaction Device** | ships a **`human-mock`** (`src/human_mock.cpp` or `HumanMock.java`): a standalone runnable that simulates the physiological signal source and normal operator actions for that device and emits them as the generated message types. |
| **Fixed infrastructure** (HMS, Point of Information, Ward Information Integrator) | C++ / CMake, **`device_app` only, no `human-mock`**. It is a hub: data it publishes is `push`, data it ingests / caches is `pull`. |
| **Network Outbound** data | `push` messages (`stream` if continuous, `event` if an alarm/discrete), with a table name when it is a record. |
| **Network Inbound** data | `pull` messages; recurring ones (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`) live once in `_shared/common.harpia`. |

## The 20 projects

| Room | Device | Target | Human-mock |
|---|---|---|---|
| 0 hospital management and information | [Hospital Management System](./0-hospital-management-and-information/hospital-management-system) | C++ / CMake | no |
| 0 hospital management and information | [Hospital Point of Information](./0-hospital-management-and-information/hospital-point-of-information) | C++ / CMake | no |
| 1 intensive care unit | [Multiparameter Patient Monitor](./1-intensive-care-unit/multiparameter-patient-monitor) | Java / Android | yes |
| 1 intensive care unit | [Mechanical Ventilator](./1-intensive-care-unit/mechanical-ventilator) | C++ / CMake | yes |
| 1 intensive care unit | [Infusion Pump](./1-intensive-care-unit/infusion-pump) | C++ / CMake | yes |
| 1 intensive care unit | [Intracranial Pressure (ICP) Monitor](./1-intensive-care-unit/intracranial-pressure-monitor) | Java / Android | yes |
| 1 intensive care unit | [Ward Information Integrator — ICU](./1-intensive-care-unit/ward-information-integrator) | C++ / CMake | no |
| 2 operating room | [Anesthesia Machine](./2-operating-room/anesthesia-machine) | Java / Android | yes |
| 2 operating room | [Heart-Lung Machine](./2-operating-room/heart-lung-machine) | C++ / CMake | yes |
| 2 operating room | [Surgical Robot Console](./2-operating-room/surgical-robot-console) | C++ / CMake | yes |
| 2 operating room | [Endoscopy Video Tower](./2-operating-room/endoscopy-video-tower) | C++ / CMake | yes |
| 2 operating room | [Ward Information Integrator — OR](./2-operating-room/ward-information-integrator) | C++ / CMake | no |
| 3 general patient ward | [Electronic Hospital Bed](./3-general-patient-ward/electronic-hospital-bed) | Java / Android | yes |
| 3 general patient ward | [Sequential Compression Device (SCD)](./3-general-patient-ward/sequential-compression-device) | C++ / CMake | yes |
| 3 general patient ward | [Feeding Pump](./3-general-patient-ward/feeding-pump) | C++ / CMake | yes |
| 3 general patient ward | [Bladder Scanner](./3-general-patient-ward/bladder-scanner) | Java / Android | yes |
| 3 general patient ward | [Ward Information Integrator — General Patient Ward](./3-general-patient-ward/ward-information-integrator) | C++ / CMake | no |
| 4 mobile and handheld support network | [Doctor's Tablet](./4-mobile-and-handheld-support-network/doctors-tablet) | Java / Android | no |
| 4 mobile and handheld support network | [Crash Cart Defibrillator](./4-mobile-and-handheld-support-network/crash-cart-defibrillator) | C++ / CMake | yes |
| 4 mobile and handheld support network | [Patient Telemetry Pack](./4-mobile-and-handheld-support-network/patient-telemetry-pack) | Java / Android | yes |

## Helper scripts

Drive every project through the repo's helper scripts rather than ad-hoc
commands:

| Script | Use |
|---|---|
| [`../run_harpia.sh`](../run_harpia.sh) `<projdir> <outdir> --no-build` | generate the **C++** target from a project folder (codegen only -- do not run the generated ctest suite, it is slow) |
| [`../docker/run.sh`](../docker/run.sh) `bash -c '...'` | run `cmake` / `gradle` / the Java-target `HARPIA_GEN_LANG=java python3 main.py` inside the `harpia-build` image when there is no host toolchain |

Each project `README.md` spells out the exact commands for that project, in
both the host-toolchain and all-in-Docker forms.

**First generation of a brand-new project:** the pipeline writes a
`schema_registry/` sidecar next to the `.harpia` on the first run (frozen wire
numbers), which needs the project folder writable. `run_harpia.sh` detects this
— when the input folder has no `schema_registry/` yet it mounts the input
**read-write** for that one run (it prints `mount : input mounted READ-WRITE
(first generation…)`), and reverts to read-only once the sidecar exists. Just
run `run_harpia.sh` as normal and **commit the resulting `schema_registry/`**.

## Start here

Pick any project and follow its `README.md`. A good first read is
[`1-intensive-care-unit/mechanical-ventilator`](./1-intensive-care-unit/mechanical-ventilator)
(C++) or
[`1-intensive-care-unit/multiparameter-patient-monitor`](./1-intensive-care-unit/multiparameter-patient-monitor)
(Java/Android).
