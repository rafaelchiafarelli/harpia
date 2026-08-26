# Epic: Mobile And Handheld Support Network  (4-mobile-and-handheld-support-network)

Devices from the `4-mobile-and-handheld-support-network` room of `TestProjects/Projects.md`. Goal per device:
a harpia project that generates and a `device_app` (+ `human_mock` where the
device is a Human Interaction Device) that builds and runs.

| Device | Target | Human-mock | Status |
|---|---|---|---|
| [doctors-tablet](histories/doctors-tablet/) | Java / Android | no | not started |
| [crash-cart-defibrillator](histories/crash-cart-defibrillator/) | C++ / CMake | yes | not started |
| [patient-telemetry-pack](histories/patient-telemetry-pack/) | Java / Android | yes | not started |

This section is not a ward and has no Ward Information Integrator of its own.
Each device here binds to the integrator for its current physical location and
is handed off between integrators as it moves; the Doctor's Tablet also holds a
direct HMS session for historical charts. See the Connectivity Map at the end
of `TestProjects/Projects.md`.

Project sources: [`../../../../TestProjects/4-mobile-and-handheld-support-network/`](../../../../TestProjects/4-mobile-and-handheld-support-network/).
Per-device history: `histories/<device>/`.
