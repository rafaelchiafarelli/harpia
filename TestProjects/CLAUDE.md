# TestProjects -- worked harpia example projects (reference material, not on the pipeline)

**Role:** 20 small example projects derived from `Projects.md` (the "Hospital
Electronic Equipment & Network Data Blueprint"): one per medical device (15),
plus 5 facility-infrastructure hubs added 2026-08-26 -- the Hospital Management
System, the Hospital Point of Information (both under `0-.../`), and one Ward
Information Integrator per clinical ward (in `1-.../`, `2-.../`, `3-.../`).
Grouped by clinical environment (blueprint sections 0-4). Each *creates and
consumes* harpia-generated code -- same role as `HarpiaTest/app_example/consumer` /
`HarpiaTest/app_example/android_consumer`. Nothing here is read by `main.py`, `Util/`, or
`tests/`.

## Contents
- `Projects.md` -- the source blueprint: 15 devices + 5 infrastructure hubs (HMS, Point of Information, 3 Ward Information Integrators) x {Main Features, Network Outbound, Network Inbound, Human Interaction Device?, Mobile device?, Fixed infrastructure?}, plus a **Connectivity Map** at the end (centralized hub-and-spoke: device -> ward integrator -> HMS; no device-to-device sockets).
- `_shared/common.harpia` -- shared inbound message types (`patient_demographics`, `clock_sync`, `clinician_identity`, `device_location`); copied verbatim into every project's `Include/`.
- `<n>-<room>/<device>/` -- per project: `<name>.harpia` (assembled schema), `Include/common.harpia`, `src/`, `README.md` (the blueprint bullets for that device are inlined at the top of its `README.md`), and build infra.
- `Requisits.md`, `Example.md` -- the older feature-checklist / domain-example seed notes (kept).
- `CMakeLists.txt` -- pre-existing one-line stub, unrelated to the per-project builds.

## Derivation rules (see README.md for the table)
- "Mobile device" -> Java target, single-module Android app module (Gradle, AGP 8.2.2).
- otherwise -> C++ target, CMake + vcpkg (modelled on `HarpiaTest/app_example/consumer`).
- "Human Interaction Device" -> a `human-mock` runnable (`src/human_mock.cpp` / `HumanMock.java`) that generates simulated physiological + operator traffic as the generated message types.
- "Fixed infrastructure" (HMS, Point of Information, Ward Information Integrator) -> C++ target, `device_app` only, **no `human_mock`**. Data the hub publishes -> `push`; data it ingests / caches -> `pull`.
- Network Outbound -> `push`/`stream`/`event` messages; Network Inbound -> `pull`; recurring inbound types factored into `_shared/common.harpia`.

## Key facts / gotchas
- `.harpia` authoring constraints that bit here: no `bool` type (use `int` 0/1); `optional `/`required `/`phi ` need a trailing space; `repeteable` is spelled that way; every `enum` needs one `= 0`; files must be ASCII and end in a newline; `.harpia` **comments** may only contain letters/digits/space and `. , ( ) { } [ ] ; = < > + - * /` -- a `:` `'` `%` etc. anywhere (even in a comment) hard-errors the file.
- **`int` maps to proto `int32`** -- keep int literals in the demo `.cpp` under 2^31.
- Two generator bugs hit while scaffolding these projects were **fixed on `dev` (commit `045123f`) and merged into this branch**: (1) the lexer matched bare-word type keywords (`int`, `int64`, `float`, `string`, `map`, `import`, `repeteable`, `pagination`) as identifier *prefixes* -- `integrator_link_state` lexed as `int` + `egrator_link_state` -> `NO_NAME_IN_MESSAGE`; now `\b`-anchored, so `int`/`string`-prefixed names are fine. (2) `run_harpia.sh` mounted the input `:ro`, so the first-ever generation (which writes `schema_registry/`) failed; it now auto-mounts read-write when there is no `schema_registry/` yet. Just run `run_harpia.sh` normally.
- Generated identifiers are md5-hash-qualified off the `.harpia` input; the C++ `CMakeLists.txt` globs generated headers into a `harpia_generated_includes.h` so no project hard-codes a hash.
- Each project folder is a valid `run_harpia.sh` input folder: exactly one root `.harpia` at its top level, plus `Include/`.
- On first generation the pipeline drops a `schema_registry/` sidecar next to each `.harpia` (stable field numbers). It is **git-ignored repo-wide** (`.gitignore`: `schema_registry/`) -- regenerate it locally, do not commit or hand-edit.
