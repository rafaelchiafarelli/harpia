# Epic: General Patient Ward  (3-general-patient-ward)

Devices from the `3-general-patient-ward` room of `TestProjects/Projects.md`. Goal per device:
a harpia project that generates and a `device_app` (+ `human_mock` where the
device is a Human Interaction Device) that builds and runs.

| Device | Target | Human-mock | Status |
|---|---|---|---|
| [electronic-hospital-bed](histories/electronic-hospital-bed/) | Java / Android | yes | not started |
| [sequential-compression-device](histories/sequential-compression-device/) | C++ / CMake | yes | not started |
| [feeding-pump](histories/feeding-pump/) | C++ / CMake | yes | not started |
| [bladder-scanner](histories/bladder-scanner/) | Java / Android | yes | not started |
| [ward-information-integrator](histories/ward-information-integrator/) | C++ / CMake | no | scaffold generates + builds + runs `device_app`; hub wiring not started |

The **ward-information-integrator** is facility infrastructure, not a bedside
device: it is the ward's edge hub (every general-ward device connects to it; it
relays up to the HMS). See the Connectivity Map at the end of
`TestProjects/Projects.md`.

Project sources: [`../../../../TestProjects/3-general-patient-ward/`](../../../../TestProjects/3-general-patient-ward/).
Per-device history: `histories/<device>/`.
