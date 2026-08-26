### Ward Information Integrator — ICU
*   **Main Features:** Ward-local edge server that aggregates every ICU device onto one fabric. Runs as a local publish/subscribe broker so bedside events (alarms, live vitals, ICP threshold breaches) reach other ICU endpoints in real time, and as a store-and-forward gateway that relays the same data up to the HMS. Caches HMS reference data (demographics, orders, care-team, clock) locally so the ICU keeps functioning through an HMS or WAN outage, and serves as the ward's local clock stratum.
*   **📡 Network Outbound:** Aggregated ICU telemetry and alarm streams, per-device health and audit logs, and store-and-forward replay batches — all to the HMS.
*   **📥 Network Inbound:** Patient demographics, electronic prescriptions, ADT status, clinician identity, device-to-bed assignments, and clock sync — from the HMS, for local redistribution to ICU devices.
*   **🔀 Ward Information Integrator**
*   **Fixed infrastructure** (Rack- or wall-mounted ward server, redundant pair recommended; no patient contact, not mobile).
