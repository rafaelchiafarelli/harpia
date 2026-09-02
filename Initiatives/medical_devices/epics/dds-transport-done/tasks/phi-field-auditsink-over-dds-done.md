## `phi` field `AuditSink` wiring over DDS

Scoped 2026-08-29. **Task 4** of the dds-transport epic. Parallel with task 3
(`dds-security-wiring`) — both depend only on task 2b.

- **Depends on:** task 2b (`dds-adapter-qos-mapping`) merged; F3 (Foundation)
  `AuditSink`.
- **Deliverable:** a `phi` field crossing the DDS transport triggers the
  same `AuditSink` call pattern the db-encryption epic already establishes for
  DB and event delivery — the transport changes, the audit obligation
  doesn't. **Recommended operation name:** `phi_publish`, `subject` = the
  message / DDS topic name, `detail` = the `phi` field names — never a
  value (design-rules Rule 5). Confirm against the DB pattern
  (`phi_create` / `phi_read` / ...) when implementing.
- **Tests:**
  - Integration: a `phi` field over DDS emits exactly one `AuditSink`
    record per publish, `detail` carries names only, matching the
    db-encryption epic's pattern (`UnitTests/test_stage8_db.py::test_a3_*`
    shape).

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
