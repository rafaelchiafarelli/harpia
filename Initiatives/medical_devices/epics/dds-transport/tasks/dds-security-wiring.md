
## DDS-Security wiring

Scoped 2026-08-29. **Task 3** of the dds-transport epic. Parallel with task 4
(`phi-field-auditsink-over-dds`) — both depend only on task 2b, not on each
other.

- **Depends on:** task 2b (`dds-adapter-qos-mapping`) merged; F5 (Foundation).
- **Pre-work (inside this task, once 2a's vendor is known):** generated
  DDS-Security governance + permissions XML templates and a build-time
  certificate/identity provisioning probe, mirroring
  `Assets/cmake/curve_keygen_probe.cpp` (the CURVE keygen probe) and
  transport-authn's planned mTLS cert provisioning. The exact governance/
  permissions XML shape is implementation-specific, so it is confirmed
  against the vendor task 2a committed, not guessed here.
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
