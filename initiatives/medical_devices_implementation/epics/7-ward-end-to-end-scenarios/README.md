# Epic: Ward End-to-End Scenarios  (7-ward-end-to-end-scenarios)

Cross-cutting epic. Once a ward's devices + integrator + HMS each build and run
(room epics) and are wired to talk (epic 5), run a **whole ward as one
scenario**: every device's `human_mock` feeding its `device_app`, the integrator
brokering ward-internal events and relaying up, the HMS ingesting, a Point of
Information showing the result.

Depends on: epic 5 (transport & hub wiring), and epic 6 for the Java devices in
each ward.

| Scenario | Scope | Status |
|---|---|---|
| [harness](histories/harness/) | The scripting that stands a scenario up (several `docker/run.sh` processes, or one compose), tears it down, and defines what "passing" looks like. | not started |
| [icu-e2e](histories/icu-e2e/) | 4 ICU devices + ICU integrator + HMS + a Point of Information, running together. | not started |
| [or-e2e](histories/or-e2e/) | 4 OR devices + OR integrator + HMS + a Point of Information. | not started |
| [general-ward-e2e](histories/general-ward-e2e/) | 4 general-ward devices + ward integrator + HMS + a Point of Information. | not started |
| [mobile-roaming-handoff](histories/mobile-roaming-handoff/) | Patient Telemetry Pack / Doctor's Tablet moving between ward integrators; the Doctor's Tablet's direct HMS session for historical charts. | not started |

Reference: Connectivity Map, end of
[`../../../../TestProjects/Projects.md`](../../../../TestProjects/Projects.md).
Per-scenario history: `histories/<scenario>/`.
