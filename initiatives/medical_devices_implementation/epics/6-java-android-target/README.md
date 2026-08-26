# Epic: Java / Android Target Build-Out  (6-java-android-target)

Cross-cutting epic. 7 of the 20 projects are Java / Android and none is started.
The room epics list them, but the Java path — build-time codegen with
`HARPIA_GEN_LANG=java`, a single-module Android app (Gradle, AGP 8.2.2),
`com.harpia.runtime.json.HarpiaJson`, JeroMQ / CURVE — is a distinct toolchain
from the C++ CMake path. This epic owns that shared path and drives all 7 to a
**building + running Android app module**, modelled on
`examples/android_consumer`.

The room epic's history for each Java device still records its own build/run
result; this epic holds the shared recipe and the cross-device gotchas.

| Slice / device | Room | human_mock | Status |
|---|---|---|---|
| [shared-toolchain-path](histories/shared-toolchain-path/) | — | — | not started — the Gradle / `HARPIA_GEN_LANG=java` recipe + first device end-to-end |
| [multiparameter-patient-monitor](histories/multiparameter-patient-monitor/) | 1 ICU | yes | not started |
| [intracranial-pressure-monitor](histories/intracranial-pressure-monitor/) | 1 ICU | yes | not started |
| [anesthesia-machine](histories/anesthesia-machine/) | 2 OR | yes | not started |
| [electronic-hospital-bed](histories/electronic-hospital-bed/) | 3 Ward | yes | not started |
| [bladder-scanner](histories/bladder-scanner/) | 3 Ward | yes | not started |
| [doctors-tablet](histories/doctors-tablet/) | 4 Mobile | no | not started |
| [patient-telemetry-pack](histories/patient-telemetry-pack/) | 4 Mobile | yes | not started |

Reference: `examples/android_consumer/README.md` and each device's own
`TestProjects/<room>/<device>/README.md`.
Per-device history: `histories/<device>/`.
