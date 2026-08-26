### Ward Information Integrator — OR
*   **Main Features:** Theatre-local edge server that aggregates every OR device onto one fabric. Brokers intra-theatre traffic (case events, gas/flow alarms, calibration status) in real time and relays it up to the HMS. Caches the pre-surgical checklist, case validation records and surgeon identities locally so a running case is unaffected by an HMS or WAN outage, and holds the theatre's local clock stratum for procedural timestamp markers. High-bandwidth video (robot console, endoscopy tower) is routed on a separate in-theatre A/V path and is not carried on this data fabric.
*   **📡 Network Outbound:** Aggregated OR telemetry and alarm streams, per-device calibration and audit logs, and store-and-forward replay batches — all to the HMS.
*   **📥 Network Inbound:** Pre-surgical checklists, active case validation records, surgeon login profiles, patient ID assignment tags, and procedural timestamp sync — from the HMS, for local redistribution to OR devices.
*   **🔀 Ward Information Integrator**
*   **Fixed infrastructure** (Rack-mounted theatre server, redundant pair recommended; no patient contact, not mobile).
