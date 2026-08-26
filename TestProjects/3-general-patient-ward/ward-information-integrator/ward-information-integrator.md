### Ward Information Integrator — General Patient Ward
*   **Main Features:** Ward-local edge server that aggregates every general-ward device onto one fabric. Brokers ward-internal events (bed-exit alerts, SCD/feed occlusion alarms, bladder-scan completions) to the nurses' station and Points of Information in real time, and relays the same data up to the HMS. Caches HMS reference data (nutrition plans, nurse identity, bed assignments, location pings) locally so the ward keeps functioning through an HMS or WAN outage, and serves as the ward's local clock stratum.
*   **📡 Network Outbound:** Aggregated ward telemetry and alarm streams, per-device health and audit logs, and store-and-forward replay batches — all to the HMS.
*   **📥 Network Inbound:** Scheduled nutrition plans, assigned nurse login IDs, patient record match tags, remote bed-lock reset commands, and device location update pings — from the HMS, for local redistribution to ward devices.
*   **🔀 Ward Information Integrator**
*   **Fixed infrastructure** (Wall-mounted ward server, redundant pair recommended; no patient contact, not mobile).
