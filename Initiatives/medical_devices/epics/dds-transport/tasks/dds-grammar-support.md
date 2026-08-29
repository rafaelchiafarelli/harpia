## `dds` grammar support

- **Depends on:** F1 (Foundation).
- **Deliverable:** new `dds` transport-modifier value in
  `LexicalAnalizer/`/`Message/`, composable the same way `push`/`pull`/
  `event`/`stream` are today — a message picks `dds` when it needs to be
  published onto/read from a DDS bus, independent of whether it's also
  reachable via ZMQ or gRPC.
- **Tests:**
  - Unit: `dds` composes correctly with `phi`, `optional`, `repeteable`
    per existing modifier-composition tests.

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
