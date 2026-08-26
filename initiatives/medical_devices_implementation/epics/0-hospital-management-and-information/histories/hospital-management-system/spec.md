# Spec — Hospital Management System (HMS)

History folder for the **Hospital Management System** component of epic
`0-hospital-management-and-information`. This file is the "what to do" for the
component; session notes / decisions / what-built-and-ran go in sibling files
as the work happens.

Project source:
[`../../../../../../TestProjects/0-hospital-management-and-information/hospital-management-system/`](../../../../../../TestProjects/0-hospital-management-and-information/hospital-management-system/)
— its `README.md` carries the blueprint bullets for this component. Wiring
context: the Connectivity Map at the end of `TestProjects/Projects.md`.

## Role (from the blueprint)

The **central facility backend**. Every ward device connects only to its Ward
Information Integrator; every integrator connects to the HMS. The HMS is the
source of most inbound reference data the wards consume and the sink for the
telemetry / alarms / audit they produce. Fixed infrastructure → C++ / CMake,
single `device_app` target, **no `human_mock`**.

## Current state (2026-08-26)

Scaffold **generates + builds + runs**. `run_harpia.sh` produces the C++
target; `device_app` constructs each published message and prints it as JSON,
then exits. Nothing is wired: no transport, no DB, no north/south interface.
The `pull` ingest messages in the schema are declared but never exercised.

Schema already in place (`hospital_management_system.harpia`):

| Direction | Messages |
|---|---|
| `push event` (HMS is the source) | `adt_status_update`, `prescription_release`, `nutrition_plan_release`, `authorization_token`, `device_bed_assignment`, `facility_clock_tick` |
| `pull event` (HMS ingests from wards) | `ward_telemetry_ingest`, `ward_alarm_ingest`, `device_selftest_ingest`, `audit_log_ingest` |

Every message has a `*_table`, so DB + CRUDL + REST/SOAP are generated for all
ten. `phi required string patient_id` appears on `adt_status_update`,
`prescription_release`, `nutrition_plan_release`.

## Scope — what "done" means for this component

Take the HMS from "prints JSON" to a running hub that a ward integrator can
actually talk to:

1. **Persistence.** Wire the generated CRUDL DAO for the ten record types so
   published reference data and ingested ward data survive a restart. Follow
   `examples/consumer`'s DAO wiring. SQLite backend is fine for the scaffold;
   note if/where Postgres is expected.
2. **North interface — publish reference data.** Expose the six `push`
   messages over the transport chosen in epic 5
   (`5-transport-and-hub-wiring/histories/choose-transport/`). A client
   (integrator, or a stand-in) subscribes and receives `adt_status_update`,
   `prescription_release`, `nutrition_plan_release`, `authorization_token`,
   `device_bed_assignment`, `facility_clock_tick`.
3. **South interface — ingest ward data.** Accept the four `pull` ingest
   messages from a ward integrator and land them in their tables:
   `ward_telemetry_ingest`, `ward_alarm_ingest`, `device_selftest_ingest`,
   `audit_log_ingest`.
4. **REST/CRUDL surface.** The generated REST bindings for the record types
   come up and answer, for direct queries (the "Doctor's Tablet → HMS, down:
   complete historical patient charts" edge in the Connectivity Map).
5. **`device_app` demonstrates the loop.** Instead of print-and-exit: seed
   reference data, publish it, accept a simulated ward ingest batch, read it
   back from the DB. Keep it runnable end-to-end through `run_harpia.sh` +
   `docker/run.sh`, same as the room-epic devices.

Out of scope here: store-and-forward buffering, replay, downlink caching,
local clock stratum — those live on the **integrator** side (epic 5 slices
`ward-integrator-uplink`, `ward-integrator-downlink-cache`). External EHR /
pharmacy / LIS/RIS interfaces are out of scope for the whole blueprint.

## Depends on

- **Epic 5 `choose-transport`** — the device↔integrator and integrator↔HMS
  transport decision (gRPC / ZMQ / REST are all generated). Do not pick one
  unilaterally here; record the dependency and use whatever that slice lands.
- **Epic 5 `hms-north-south`** — this component's spec and that slice describe
  the same work from two directions. Keep them consistent; if the work happens
  under one, the other should point at it rather than duplicate.
- The room-epic devices reaching "generates + builds + runs" (done for the
  C++ set) so there is a real client shape to target.

## Feeds

- **Epic 5 `ward-integrator-uplink` / `ward-integrator-downlink-cache`** — the
  integrator side of the same two edges; they consume the interface this
  component exposes.
- **Epic 7 `icu-e2e` / `general-ward-e2e` / `or-e2e`** — a whole ward run
  terminates at the HMS; those scenarios can't close until 2–4 above work.
- **Epic 8 `phi-field-inventory`** — the three `phi`-tagged `patient_id`
  fields here are part of what that audit inventories across the 20 projects.

## Files this touches

- `TestProjects/0-hospital-management-and-information/hospital-management-system/src/main.cpp`
  — the `device_app`; grows from print-and-exit to the seed/publish/ingest/
  read-back loop.
- `.../hospital-management-system/CMakeLists.txt` — link the generated DAO /
  REST / transport libs the way `examples/consumer/CMakeLists.txt` does.
- `.../hospital-management-system/hospital_management_system.harpia` +
  `Include/common.harpia` — only if a gap shows up while wiring (e.g. a field
  the integrator edge needs). Schema changes mean re-running `run_harpia.sh`;
  the regenerated `schema_registry/` sidecar is git-ignored under
  `TestProjects/`, so there is nothing to commit back.
- New non-generated glue (DAO setup, server bootstrap) under the project
  folder, mirroring `examples/consumer` layout.
- No generator changes. This initiative exercises the generator, never edits
  it.

## Watch for

- **Generated identifiers are md5-hash-qualified** off the `.harpia` input.
  `CMakeLists.txt` globs generated headers into `harpia_generated_includes.h`
  — keep using that; never hard-code a hash in project code.
- **First generation** of a brand-new message writes `schema_registry/`
  sidecars into the input folder; `run_harpia.sh` now mounts read-write on
  first gen automatically (fixed in `045123f`). Under `TestProjects/` that
  sidecar is git-ignored — regenerated locally, nothing to commit.
- **`.harpia` authoring constraints** if the schema is touched: no `bool`,
  modifier keywords need a trailing space, comment charset limits, one JSON
  header per translation unit.
- The `pull` ingest messages currently have **no exercise anywhere** — the
  scaffold `device_app` only touches the `push` side. The south interface is
  genuinely new ground for this component, not a rewire of existing code.
