## Full acceptance gate + `ComplianceReport` note

Scoped 2026-08-29. **Task 5** (final) of the dds-transport epic.

- **Depends on:** tasks 1, 2a, 2b, 3, 4 merged.
- **Deliverable:** the one-paragraph `ComplianceReport/` note — filed as a
  **process-artifacts** task (`process-artifacts/tasks/dds-transport-note.md`,
  same pattern as `serialization-redaction-note.md` /
  `phi-db-encryption-note.md` / `critical-delivery-note.md`), per
  `epics/README.md` DoD rule 6: `ComplianceReport/` is the
  process-artifacts epic's module, not this one's. The note covers the
  `dds` modifier, `DdsAdapter/`, the QoS mapping, DDS-Security wiring, and
  the `phi` audit path — what changed, why, which tests.
- **Acceptance gate:** existing ZMQ/gRPC demo tests unaffected — `dds` is
  additive, not a replacement for either. Full suite green in Docker.
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
