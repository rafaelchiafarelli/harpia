
## `DdsAdapter/` core + QoS mapping

Scoped 2026-08-29. **Task 2b** of the dds-transport epic (was task 2; the
"pick + vendor a DDS stack" half was split out to **task 2a
`dds-vendor-and-spike`** during planning). This task is pure codegen — the
DDS implementation is already vendored and build-verified by 2a.

- **Depends on:** task 2a (`dds-vendor-and-spike`) merged — the DDS
  implementation is committed and vendored; this task does not choose one.
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
- **Out of scope:** DDS-Security (task 3); `phi` audit wiring (task 4);
  choosing / vendoring the DDS implementation — that is **task 2a**
  (`dds-vendor-and-spike`), which must be merged first. This task builds
  the adapter against whatever 2a committed.
- **`DURABILITY=TRANSIENT_LOCAL` stays off** for this task (the
  late-joiner-catch-up open question is per-use-case; a `durability` knob
  is future scope, not here).
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
