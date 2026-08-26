# Epic: Hospital Management & Information  (0-hospital-management-and-information)

Facility-infrastructure components from section 0 of `TestProjects/Projects.md`.
These are not bedside devices — they are the hubs the wards connect to. Goal per
component: a harpia project that generates and a `device_app` that builds and
runs. None is a Human Interaction Device, so none ships a `human_mock`.

| Component | Target | Human-mock | Status |
|---|---|---|---|
| [hospital-management-system](histories/hospital-management-system/) | C++ / CMake | no | scaffold generates + builds + runs `device_app`; hub wiring not started |
| [hospital-point-of-information](histories/hospital-point-of-information/) | C++ / CMake | no | scaffold generates + builds + runs `device_app`; hub wiring not started |

Project sources:
[`../../../../TestProjects/0-hospital-management-and-information/`](../../../../TestProjects/0-hospital-management-and-information/).
Per-component history: `histories/<component>/`.

See the Connectivity Map at the end of `TestProjects/Projects.md` for how the
HMS, the Points of Information and the ward integrators wire together
(centralized hub-and-spoke with a ward edge tier).
