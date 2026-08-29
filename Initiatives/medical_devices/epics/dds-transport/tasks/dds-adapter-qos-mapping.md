
## `DdsAdapter/` core + QoS mapping

- **Depends on:** task 1 merged.
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
- **Out of scope:** DDS-Security (task 3); `phi` audit wiring (task 4); a
  vendored/`third_party/`-linked DDS implementation is needed to make
  this session's tests real (e.g. Eclipse Cyclone DDS — exact vendor TBD,
  prove the interface is real before committing to one, same posture as
  the key-management epic's KMS reference adapter) — pick one as part of this session,
  it's not deferred to a later one.
- **Tests:**
  - Unit: `critical`/non-`critical` messages map to the correct QoS
    profile.
  - Integration: a client/server DDS demo (mirroring the existing ZMQ
    demo in `UnitTests/test_demo.py`) — publish a `critical` and a
    non-`critical` message, confirm delivery semantics differ as
    specified under a simulated transient network gap.
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
