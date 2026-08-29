## `phi` field `AuditSink` wiring over DDS

- **Depends on:** task 2 merged; F3 (Foundation) `AuditSink`.
- **Deliverable:** a `phi` field crossing the DDS transport triggers the
  same `AuditSink` call pattern the db-encryption epic/E already establish for DB and
  event delivery — the transport changes, the audit obligation doesn't.
- **Tests:**
  - Integration: `phi` field over DDS emits exactly one `AuditSink`
    record per publish, matching the db-encryption epic/E's pattern.

---
## Epic context — dds-transport

**Contract.** A new `dds` transport modifier, a `DdsAdapter/` module mirroring
`ZmqAdapter/`, QoS mapping for `critical`/non-`critical` messages, and DDS-Security
wiring via the `CryptoBackend` seam. A third selectable transport alongside gRPC
and ZMQ (ASTM F2761 / OpenICE-class bedside bus), not a replacement. Needs
`ComplianceContext`, the `AuditSink` stub, and the `CryptoBackend` seam from
Foundation.

**Files.** New `DdsAdapter/`; `LexicalAnalizer/` and `Message/` for the `dds`
grammar.

**Open question (not scoped).** Deadline QoS (DDS detecting a publisher missing
its period) is new territory beyond the design rules §4 — whether a periodic
stream wants a schema-level `deadline[ms]` modifier needs a domain-expert pass
before it is scoped. Do not invent the name/semantics here.

**Watch for.** The DDS implementation choice (vendor TBD, e.g. Eclipse Cyclone
DDS) blocks every task after the adapter core — pick one deliberately there, do
not leave it as a follow-up.
