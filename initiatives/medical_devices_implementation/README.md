# Medical Devices Implementation

Turns the 15 worked example projects under [`../../TestProjects/`](../../TestProjects/)
(derived from `TestProjects/Projects.md`, the Hospital Electronic Equipment &
Network Data Blueprint) into a tracked implementation effort: for each device,
drive its harpia project to **buildable, runnable code** (a `device_app` that
consumes the generated code, plus a `human_mock` traffic generator for every
Human Interaction Device).

This is the *implementation* companion to `../medical_devices/` (which is the
compliance/design-rules effort). Nothing here changes the generator; it exercises
it, one device at a time.

## Structure

- `epics/` — one epic per clinical environment (room) from the blueprint.
  - `<room>/README.md` — the room's devices, their target language, and status.
  - `<room>/histories/<device>/` — the running history for that one device
    (session notes, decisions, what built and ran).

- [`epics/1-intensive-care-unit/`](epics/1-intensive-care-unit/) — 4 devices
- [`epics/2-operating-room/`](epics/2-operating-room/) — 4 devices
- [`epics/3-general-patient-ward/`](epics/3-general-patient-ward/) — 4 devices
- [`epics/4-mobile-and-handheld-support-network/`](epics/4-mobile-and-handheld-support-network/) — 3 devices

## Status

Started 2026-08-25 on branch `feature/test-projects-blueprint`. ICU room first:
`infusion-pump` and `mechanical-ventilator` (C++) generate + build + run
end-to-end via `run_harpia.sh` + `docker/run.sh`; the two Java/Android devices
and rooms 2–4 are not started.

## How each device is built

C++ device (per its `TestProjects/.../README.md`):
1. `bash ./run_harpia.sh TestProjects/<room>/<device> TestProjects/_gen/<device> --no-build`
2. `bash docker/run.sh bash -c 'cmake -S <projdir> -B <projdir>/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/<device> && cmake --build <projdir>/_build -j"$(nproc)"'`
3. `bash docker/run.sh bash -c './<projdir>/_build/device_app; ./<projdir>/_build/human_mock | head'`

Java device: `docker/run.sh` + `HARPIA_GEN_LANG=java python3 main.py`, then
Gradle against `-PharpiaGenDir` (see the device's own README).
