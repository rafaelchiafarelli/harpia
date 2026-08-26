# Medical Devices Implementation

Turns the 20 worked example projects under [`../../TestProjects/`](../../TestProjects/)
(derived from `TestProjects/Projects.md`, the Hospital Electronic Equipment &
Network Data Blueprint) into a tracked implementation effort: for each device,
drive its harpia project to **buildable, runnable code** (a `device_app` that
consumes the generated code, plus a `human_mock` traffic generator for every
Human Interaction Device).

The 20 projects are the 15 medical devices plus the 5 facility-infrastructure
components added to the blueprint on 2026-08-26: the **Hospital Management
System** (HMS), the **Hospital Point of Information**, and one **Ward
Information Integrator** per clinical ward (ICU, OR, General Patient Ward). The
infrastructure components are all C++ hubs with a single `device_app` and no
`human_mock`.

This is the *implementation* companion to `../medical_devices/` (which is the
compliance/design-rules effort). Nothing here changes the generator; it exercises
it, one device at a time.

## Structure

`epics/` holds two kinds of epic. Each `<epic>/README.md` carries the scope +
status table; each `<epic>/histories/<name>/` is one running history (session
notes, decisions, what built and ran).

### Room epics (0–4) — one per clinical environment in the blueprint

Goal per device/component: a harpia project that generates and a `device_app`
(+ `human_mock` for a Human Interaction Device) that builds and runs.

- [`epics/0-hospital-management-and-information/`](epics/0-hospital-management-and-information/) — HMS, Point of Information
- [`epics/1-intensive-care-unit/`](epics/1-intensive-care-unit/) — 4 devices + Ward Information Integrator
- [`epics/2-operating-room/`](epics/2-operating-room/) — 4 devices + Ward Information Integrator
- [`epics/3-general-patient-ward/`](epics/3-general-patient-ward/) — 4 devices + Ward Information Integrator
- [`epics/4-mobile-and-handheld-support-network/`](epics/4-mobile-and-handheld-support-network/) — 3 devices (roam between the ward integrators; no integrator of their own)

### Cross-cutting epics (5–8) — tracks the room epics don't cover

Written down 2026-08-26 as skeletons; **all not started**. Each depends on the
room epics reaching "generates + builds + runs" first.

- [`epics/5-transport-and-hub-wiring/`](epics/5-transport-and-hub-wiring/) — make the Connectivity Map real: components exchange messages over a generated transport; integrator broker + store-and-forward uplink + downlink cache; HMS north/south interfaces.
- [`epics/6-java-android-target/`](epics/6-java-android-target/) — the 7 Java/Android projects (rooms 1–4) each build + run as an Android app module via the shared Gradle / `HARPIA_GEN_LANG=java` path.
- [`epics/7-ward-end-to-end-scenarios/`](epics/7-ward-end-to-end-scenarios/) — run a whole ward together (`human_mock` → `device_app` → integrator → HMS → Point of Information); mobile roaming/handoff. Depends on 5 + 6.
- [`epics/8-phi-and-compliance-surface/`](epics/8-phi-and-compliance-surface/) — verify what the `phi ` markers + `class_c` default produce across the 20 projects. Coordinates with [`../medical_devices/`](../medical_devices/).

## Status

Started 2026-08-25 on branch `feature/test-projects-blueprint`. ICU room first:
`infusion-pump` and `mechanical-ventilator` (C++) generate + build + run
end-to-end via `run_harpia.sh` + `docker/run.sh`; the two Java/Android devices
and rooms 2–4 are not started.

2026-08-26: the 5 facility-infrastructure scaffolds (HMS, Point of Information,
and the ICU / OR / General-Ward integrators) were added and each generates +
builds + runs its `device_app` end-to-end (C++) straight through
`run_harpia.sh`. Their `device_app`s only exercise the message-class + JSON
surface so far — the real hub wiring (CRUDL DAO, REST/gRPC/ZMQ north/south
interfaces) is not started.

Two generator bugs surfaced by this scaffolding were fixed on `dev` (commit
`045123f`) and merged into this branch: the lexer no longer mis-splits
identifiers that start with a type keyword (`int`, `string`, …), and
`run_harpia.sh` now auto-mounts the input folder read-write for a brand-new
project's first generation (when it has no `schema_registry/` yet). Nothing
special is needed anymore — just run `run_harpia.sh`. The generated
`schema_registry/` sidecar is git-ignored under `TestProjects/` (throwaway
examples — regenerated locally, not committed).

Also 2026-08-26: the four cross-cutting epics (5 transport & hub wiring,
6 Java/Android target, 7 ward end-to-end scenarios, 8 PHI & compliance surface)
were written down as skeleton READMEs + history folders. All not started; each
waits on the room epics.

## How each device is built

C++ device (per its `TestProjects/.../README.md`):
1. `./run_harpia.sh TestProjects/<room>/<device> TestProjects/_gen/<device> --no-build`
2. `bash docker/run.sh bash -c 'cmake -S <projdir> -B <projdir>/_build -DHARPIA_GEN=/harpia/TestProjects/_gen/<device> && cmake --build <projdir>/_build -j"$(nproc)"'`
3. `bash docker/run.sh bash -c './<projdir>/_build/device_app; ./<projdir>/_build/human_mock | head'`

Java device: `docker/run.sh` + `HARPIA_GEN_LANG=java python3 main.py`, then
Gradle against `-PharpiaGenDir` (see the device's own README).
