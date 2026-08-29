
## DDS-Security wiring

- **Depends on:** task 2 merged; F5 (Foundation).
- **Deliverable:** OMG DDS-Security (authentication/access-control/
  encryption plugins) compiled in via the F5 `CryptoBackend` seam, one
  selection per project driven by `risk_class`/`topology` (never per
  jurisdiction, `harpia_medical_master_plan.md` §0a) — same posture as
  the transport-authn epic's mTLS and the zmq-lifecycle epic's CURVE.
- **Guarantees:** plaintext/unauthenticated DDS refused by default when
  the compliance profile requires it.
- **Out of scope, by decision:** LGPD Art. 33 / Art. 11 §4 constraints on
  where a `phi`-tagged message publishing off the bus is allowed to go
  are deployment topology and legal review, not something this epic
  enforces at compile time or runtime.
- **Tests:**
  - Integration: extend task 2's DDS demo with DDS-Security enabled, confirm
    unauthenticated peers are refused.
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
