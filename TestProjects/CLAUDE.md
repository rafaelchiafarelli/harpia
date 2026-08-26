# TestProjects -- worked harpia example projects (reference material, not on the pipeline)

**Role:** 15 small example projects derived from `Projects.md` (the "Hospital
Electronic Equipment & Network Data Blueprint"), one per medical device, grouped
by the 4 clinical environments. Each *creates and consumes* harpia-generated
code -- same role as `examples/consumer` / `examples/android_consumer`. Nothing
here is read by `main.py`, `Util/`, or `tests/`.

## Contents
- `Projects.md` -- the source blueprint: 15 devices x {Main Features, Network Outbound, Network Inbound, Human Interaction Device?, Mobile device?}.
- `_shared/common.harpia` -- shared inbound message types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`); copied verbatim into every project's `Include/`.
- `<n>-<room>/<device>/` -- per project: `<device>.md` (verbatim blueprint lines), `<name>.harpia` (assembled schema), `Include/common.harpia`, `src/`, `README.md`, and build infra.
- `Requisits.md`, `Example.md` -- the older feature-checklist / domain-example seed notes (kept).
- `CMakeLists.txt` -- pre-existing one-line stub, unrelated to the per-project builds.

## Derivation rules (see README.md for the table)
- "Mobile device" -> Java target, single-module Android app module (Gradle, AGP 8.2.2).
- otherwise -> C++ target, CMake + vcpkg (modelled on `examples/consumer`).
- "Human Interaction Device" -> a `human-mock` runnable (`src/human_mock.cpp` / `HumanMock.java`) that generates simulated physiological + operator traffic as the generated message types.
- Network Outbound -> `push`/`stream`/`event` messages; Network Inbound -> `pull`; recurring inbound types factored into `_shared/common.harpia`.

## Key facts / gotchas
- `.harpia` authoring constraints that bit here: no `bool` type (use `int` 0/1); `optional `/`required `/`phi ` need a trailing space; `repeteable` is spelled that way; every `enum` needs one `= 0`; files must be ASCII and end in a newline; `.harpia` **comments** may only contain letters/digits/space and `. , ( ) { } [ ] ; = < > + - * /` -- a `:` `'` `%` etc. anywhere (even in a comment) hard-errors the file.
- Generated identifiers are md5-hash-qualified off the `.harpia` input; the C++ `CMakeLists.txt` globs generated headers into a `harpia_generated_includes.h` so no project hard-codes a hash.
- Each project folder is a valid `run_harpia.sh` input folder: exactly one root `.harpia` at its top level, plus `Include/`.
- On first generation the pipeline drops a `schema_registry/` sidecar next to each `.harpia` (stable field numbers) -- committed source, do not hand-edit.
