# Epic: Operating Room  (2-operating-room)

Devices from the `2-operating-room` room of `TestProjects/Projects.md`. Goal per device:
a harpia project that generates and a `device_app` (+ `human_mock` where the
device is a Human Interaction Device) that builds and runs.

| Device | Target | Human-mock | Status |
|---|---|---|---|
| [anesthesia-machine](histories/anesthesia-machine/) | Java / Android | yes | not started |
| [heart-lung-machine](histories/heart-lung-machine/) | C++ / CMake | yes | not started |
| [surgical-robot-console](histories/surgical-robot-console/) | C++ / CMake | yes | not started |
| [endoscopy-video-tower](histories/endoscopy-video-tower/) | C++ / CMake | yes | not started |
| [ward-information-integrator](histories/ward-information-integrator/) | C++ / CMake | no | scaffold generates + builds + runs `device_app`; hub wiring not started |

The **ward-information-integrator** is facility infrastructure, not a theatre
device: it is the OR's edge hub (every OR device connects to it; it relays up to
the HMS). High-bandwidth surgical video stays on a separate A/V path. See the
Connectivity Map at the end of `TestProjects/Projects.md`.

Project sources: [`../../../../TestProjects/2-operating-room/`](../../../../TestProjects/2-operating-room/).
Per-device history: `histories/<device>/`.
