# Epic: Intensive Care Unit  (1-intensive-care-unit)

Devices from the `1-intensive-care-unit` room of `TestProjects/Projects.md`. Goal per device:
a harpia project that generates and a `device_app` (+ `human_mock` where the
device is a Human Interaction Device) that builds and runs.

| Device | Target | Human-mock | Status |
|---|---|---|---|
| [multiparameter-patient-monitor](histories/multiparameter-patient-monitor/) | Java / Android | yes | not started |
| [mechanical-ventilator](histories/mechanical-ventilator/) | C++ / CMake | yes | not started |
| [infusion-pump](histories/infusion-pump/) | C++ / CMake | yes | not started |
| [intracranial-pressure-monitor](histories/intracranial-pressure-monitor/) | Java / Android | yes | not started |
| [ward-information-integrator](histories/ward-information-integrator/) | C++ / CMake | no | scaffold generates + builds + runs `device_app`; hub wiring not started |

The **ward-information-integrator** is facility infrastructure, not a bedside
device: it is the ICU's edge hub (every ICU device connects to it; it relays up
to the HMS). See the Connectivity Map at the end of `TestProjects/Projects.md`.

Project sources: [`../../../../TestProjects/1-intensive-care-unit/`](../../../../TestProjects/1-intensive-care-unit/).
Per-device history: `histories/<device>/`.
