# Epic: Transport & Hub Wiring  (5-transport-and-hub-wiring)

Cross-cutting epic. The room epics (0–4) take each project to "generates +
`device_app` builds and runs", but every `device_app` so far only *constructs*
its messages and prints them as JSON. This epic makes the **Connectivity Map**
at the end of `TestProjects/Projects.md` real: components actually exchange
those messages over a harpia-generated transport, and the hubs take on their
three roles — local broker, store-and-forward uplink, downlink cache.

Nothing here changes the generator; it wires the generated gRPC / ZMQ / REST
surfaces the same way `examples/consumer` and `examples/android_consumer` do.

Depends on: the relevant room-epic devices reaching "generates + builds + runs".

| Slice | Scope | Status |
|---|---|---|
| [choose-transport](histories/choose-transport/) | Pick the transport for the device↔integrator and integrator↔HMS edges (gRPC / ZMQ / REST are all generated); record the decision and why. | not started |
| [hms-north-south](histories/hms-north-south/) | HMS publishes reference data (ADT, prescriptions, clock, device-to-bed map) and ingests ward telemetry / alarms / audit; CRUDL + REST for its record types. | not started |
| [ward-integrator-broker](histories/ward-integrator-broker/) | Integrator local pub/sub fan-out for the ward-internal edges (Connectivity Map's second table) — no HMS round trip. | not started |
| [ward-integrator-uplink](histories/ward-integrator-uplink/) | Integrator → HMS relay with store-and-forward buffering + replay; `integrator_link_status` reflects the link state. | not started |
| [ward-integrator-downlink-cache](histories/ward-integrator-downlink-cache/) | Integrator caches the `common.harpia` reference types + its ward-specific cache and serves them to ward devices; acts as local clock stratum. | not started |
| [device-client-wiring](histories/device-client-wiring/) | Each `device_app` publishes its push/stream/event and pulls its pull messages against its integrator — one representative C++ and one Java device first, then the rest. | not started |
| [point-of-information-wiring](histories/point-of-information-wiring/) | POI pulls its display data from the ward integrator and pushes interaction events back. | not started |

Reference: Connectivity Map, end of
[`../../../../TestProjects/Projects.md`](../../../../TestProjects/Projects.md).
Per-slice history: `histories/<slice>/`.
