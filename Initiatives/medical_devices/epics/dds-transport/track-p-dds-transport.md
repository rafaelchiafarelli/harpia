# Track P — DDS transport adapter (ASTM F2761/OpenICE-class bedside bus)

**Why DDS, specifically:** ASTM F2761 (the ICE — Integrated Clinical
Environment — standard) and its reference implementation, OpenICE, use
OMG DDS as the interconnect for bedside device coordination (ventilator,
infusion pump, patient monitor, etc. on one clinical network). This is a
third selectable transport alongside gRPC (Track C) and ZMQ (Track B) —
not a replacement for either.

## Receives (must be done before this track starts)

- **F1, F3, F5** from Foundation (see `../thread-5-device-interop/README.md`)
  — `ComplianceContext`, `AuditSink` stub (P.4 wires a call into it), and
  the `CryptoBackend` selection seam this track's DDS-Security wiring
  must link against (not its own crypto library).
- Nothing from Track Q — Track Q is sequenced after only because it
  benefits from this track's QoS mapping as a worked precedent, not a
  file or interface dependency.

## Gives (what "done" means here, consumed by whom)

- A new `dds` transport modifier, a `DdsAdapter/` module mirroring
  `ZmqAdapter/`'s shape, QoS mapping for `critical`/non-`critical`
  messages, and DDS-Security wiring.
- **Consumed by:** Track Q (`track-q-sdc-biceps.md`) — not a file/interface
  dependency, but its design work explicitly leans on this track's QoS/
  delivery-guarantee mapping as a precedent for how a new transport ties
  into `phi`/`critical` schema-level modifiers.

## Files this track touches

- New `DdsAdapter/` (per `harpia_medical_master_plan.md` §2's track
  table). The detailed contract also names `LexicalAnalizer/` and
  `Message/` for the `dds` grammar support (P.1 below) — not in the §2
  summary table, but explicit in the per-track contract text.

---

## Open questions (not scoped into any session above — flagged, not decided)

- **Deadline QoS** (DDS can detect a publisher missing its expected
  period) is new territory beyond `harpia_sensitive_data_design_rules.md`
  §4. Whether a periodic stream (e.g. heart rate) wants a schema-level
  `deadline[ms]` modifier that DDS enforces and `AuditSink` records a
  violation of needs a domain-expert pass before it's scoped into a
  session — don't invent the modifier name or semantics here.

## Watch for

- P.2's DDS implementation choice (vendor TBD) blocks every session after
  it — pick one deliberately as part of P.2, don't leave it as a
  follow-up.
