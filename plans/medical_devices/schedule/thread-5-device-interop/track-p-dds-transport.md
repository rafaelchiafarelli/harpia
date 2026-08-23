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

## Session P.1 — `dds` grammar support

- **Depends on:** F1 (Foundation).
- **Deliverable:** new `dds` transport-modifier value in
  `LexicalAnalizer/`/`Message/`, composable the same way `push`/`pull`/
  `event`/`stream` are today — a message picks `dds` when it needs to be
  published onto/read from a DDS bus, independent of whether it's also
  reachable via ZMQ or gRPC.
- **Tests:**
  - Unit: `dds` composes correctly with `phi`, `optional`, `repeteable`
    per existing modifier-composition tests.

## Session P.2 — `DdsAdapter/` core + QoS mapping

- **Depends on:** P.1 merged.
- **Deliverable:** new `DdsAdapter/` module mirroring `ZmqAdapter/`'s
  shape (filter messages by the `dds` modifier, template-rendered
  publisher/subscriber); QoS mapping reusing
  `harpia_sensitive_data_design_rules.md` §4's existing ordered/complete
  vs. latest-value-only split:
  - Ordered/complete (`critical`-style) → `RELIABILITY=RELIABLE`,
    `HISTORY=KEEP_ALL`, bounded via `resource_limits` (same queue-depth
    reasoning as §4a). `DURABILITY=TRANSIENT_LOCAL` for late-joiner
    catch-up is an **open question, decide per use case** — don't
    default it on for this session.
  - Latest-value-only → `RELIABILITY=BEST_EFFORT`, `HISTORY=KEEP_LAST(1)`.
- **Out of scope:** DDS-Security (P.3); `phi` audit wiring (P.4); a
  vendored/`third_party/`-linked DDS implementation is needed to make
  this session's tests real (e.g. Eclipse Cyclone DDS — exact vendor TBD,
  prove the interface is real before committing to one, same posture as
  Track O's KMS reference adapter) — pick one as part of this session,
  it's not deferred to a later one.
- **Tests:**
  - Unit: `critical`/non-`critical` messages map to the correct QoS
    profile.
  - Integration: a client/server DDS demo (mirroring the existing ZMQ
    demo in `tests/test_demo.py`) — publish a `critical` and a
    non-`critical` message, confirm delivery semantics differ as
    specified under a simulated transient network gap.

## Session P.3 — DDS-Security wiring

- **Depends on:** P.2 merged; F5 (Foundation).
- **Deliverable:** OMG DDS-Security (authentication/access-control/
  encryption plugins) compiled in via the F5 `CryptoBackend` seam, one
  selection per project driven by `risk_class`/`topology` (never per
  jurisdiction, `harpia_medical_master_plan.md` §0a) — same posture as
  Track C's mTLS and Track B's CURVE.
- **Guarantees:** plaintext/unauthenticated DDS refused by default when
  the compliance profile requires it.
- **Out of scope, by decision:** LGPD Art. 33 / Art. 11 §4 constraints on
  where a `phi`-tagged message publishing off the bus is allowed to go
  are deployment topology and legal review, not something this track
  enforces at compile time or runtime.
- **Tests:**
  - Integration: extend P.2's DDS demo with DDS-Security enabled, confirm
    unauthenticated peers are refused.

## Session P.4 — `phi` field `AuditSink` wiring over DDS

- **Depends on:** P.2 merged; F3 (Foundation) `AuditSink`.
- **Deliverable:** a `phi` field crossing the DDS transport triggers the
  same `AuditSink` call pattern Track A/E already establish for DB and
  event delivery — the transport changes, the audit obligation doesn't.
- **Tests:**
  - Integration: `phi` field over DDS emits exactly one `AuditSink`
    record per publish, matching Track A/E's pattern.

## Session P.5 — Full acceptance gate + `ComplianceReport` note

- **Depends on:** P.1–P.4 merged.
- **Deliverable:** one-paragraph `ComplianceReport/` note describing what
  changed and why (feeds Track M later).
- **Acceptance gate:** existing ZMQ/gRPC demo tests unaffected — `dds` is
  additive, not a replacement for either.

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
