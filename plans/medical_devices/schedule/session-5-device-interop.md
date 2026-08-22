# Session 5 — Device Interoperability

Covers Track P (DDS transport) and Track Q (IEEE 11073 SDC/BICEPS
bindings, scoping only). Added after the original four sessions were
scoped — see the master plan's 2026-08-21 update note. One session
handles both tracks, in order.

---

## Preconditions

- Foundation (F1, F3, F5) merged to `main` — same precondition as
  Session 2's Track C:
  - `ComplianceContext` threaded through `main.py` and every stage (F1).
  - `AuditSink` (no-op stub) exists and is injectable (F3).
  - `CryptoBackend` selection seam exists (F5) — Track P's DDS-Security
    wiring must link against this, not its own crypto library.
- For Track Q specifically: F2 (`phi` modifier) merged.
- A tagged F4 regression baseline exists.

---

## Execution order

**Track P first, then Track Q, same session.** No hard file dependency
between them, but Track Q's design work benefits from Track P's QoS/
delivery-guarantee mapping existing as a worked precedent for how a new
transport ties into the existing `phi`/`critical` schema-level modifiers.

If Session 2 finishes its four rows early, it can pick up Track P as a
next task instead of this being a strictly separate fifth session — but
keep P → Q sequential regardless of which session executes them.

---

## Contracts

### Track P — DDS transport adapter (ASTM F2761/OpenICE-class bedside bus)
- **Depends on:** F1, F3, F5.
- **Why DDS, specifically:** ASTM F2761 (the ICE — Integrated Clinical
  Environment — standard) and its reference implementation, OpenICE, use
  OMG DDS as the interconnect for bedside device coordination
  (ventilator, infusion pump, patient monitor, etc. on one clinical
  network). This is a third selectable transport alongside gRPC
  (Track C) and ZMQ (Track B) — not a replacement for either.
- **Grammar:** new `dds` transport-modifier value, composable the same
  way `push`/`pull`/`event`/`stream` are today.
- **QoS mapping reuses an existing decision, doesn't invent one:**
  `harpia_sensitive_data_design_rules.md` §4 already splits delivery
  guarantee into ordered/complete vs. latest-value-only, chosen per
  message type. Map that directly:
  - Ordered/complete (`critical`-style) → `RELIABILITY=RELIABLE`,
    `HISTORY=KEEP_ALL`, bounded via `resource_limits` (same
    queue-depth reasoning as §4a — don't pick an arbitrary depth).
    `DURABILITY=TRANSIENT_LOCAL` for late-joiner catch-up is an open
    question — decide per use case, don't default it on.
  - Latest-value-only → `RELIABILITY=BEST_EFFORT`, `HISTORY=KEEP_LAST(1)`
    — DDS's native equivalent of §4b's double-buffer mailbox.
  - **Deadline QoS is new territory beyond §4** — whether periodic
    streams (e.g. heart rate) get a schema-level `deadline[ms]` modifier
    enforced by DDS and recorded via `AuditSink` on violation is this
    track's open question to resolve, not a decision made in advance.
    Don't invent the modifier without a domain-expert pass.
- **DDS Security parity with Track B/C:** OMG DDS-Security
  (authentication/access-control/encryption plugins) compiled in via the
  F5 seam, one selection per project driven by `risk_class`/`topology`,
  never per jurisdiction (see `harpia_medical_master_plan.md` §0a) — same
  posture as Track C's mTLS and Track B's CURVE. Plaintext/unauthenticated
  DDS refused by default when the compliance profile requires it. **Out of
  scope, by decision:** LGPD Art. 33 / Art. 11 §4 constraints on where a
  `phi`-tagged message publishing off the bus is allowed to go, once it
  crosses into a different legal controller's custody, are deployment
  topology and legal review — not something Harpia enforces at compile
  time or runtime. See the master plan's Track P contract.
- **Deliverables:** new `DdsAdapter/` module (mirrors `ZmqAdapter/`'s
  shape — filter-by-modifier + template-rendered publisher/subscriber);
  a vendored/`third_party/`-linked DDS implementation (exact vendor
  TBD — e.g. Eclipse Cyclone DDS — prove the interface is real before
  committing to one, same posture as Track O's KMS reference adapter);
  DDS-Security wiring consuming F5; `dds` grammar support in
  `LexicalAnalizer/`/`Message/`.
- **Out of scope:** the BICEPS/MDPWS semantic layer (Track Q).
  Transport/QoS only, same boundary Track B keeps against Track C.
- **Tests:**
  - Unit: `critical`/non-`critical` messages map to the correct QoS
    profile; `dds` composes correctly with `phi`, `optional`,
    `repeteable`.
  - Integration: a client/server DDS demo (mirroring
    `tests/test_demo.py`'s ZMQ demo) — publish `critical` and
    non-`critical` messages, confirm delivery semantics differ as
    specified under a simulated transient network gap.
  - Integration: `phi` field over DDS emits exactly one `AuditSink`
    record per publish, matching Track A/E's pattern.
  - Acceptance gate: existing ZMQ/gRPC demo tests unaffected.

### Track Q — IEEE 11073 SDC/BICEPS bindings (scoping only)
- **Depends on:** F1, F2. Same session as Track P, after it.
- **Scope this pass is design, not implementation** — same posture the
  master plan takes with Track J. SDC (ISO/IEEE 11073-10700: BICEPS +
  MDPWS) defines a full participant/data model (MDS → VMD → Channel →
  Metric/Alert/Context), a substantially larger lift than Track P.
- **Leans on existing Stage 11 SOAP work:** MDPWS is SOAP-over-HTTP with
  WS-Discovery for peer discovery. `Database/SoapAdapter.py` and
  `Database/WsdlAdapter.py` already emit SOAP + WSDL under Track C's
  credential gate. Realistic scope: (a) a WS-Discovery probe/resolve
  responder (UDP multicast — not currently emitted anywhere), (b) a
  design doc for the Metric/Alert/Context mapping question below.
- **Open question, not a decision:** does the existing modifier
  vocabulary (`stream`, `event[cached/not-cached]`, `pull`, `push`,
  `pushpull`) map onto BICEPS Metric/Alert/Context, or does it need a
  new modifier the way `phi`/`critical` were added? A first hypothesis —
  `event` ≈ Metric, `critical event` ≈ Alert (pairs naturally with
  Track P's QoS treatment), Context needs something not yet in the
  grammar — requires a domain-expert/regulatory-affairs validation pass
  before any grammar change is locked in.
- **Deliverables (this pass):** `plans/medical_devices/sdc_biceps_design.md`
  covering the mapping question; a standalone, demonstrable WS-Discovery
  probe/resolve responder (doesn't require the mapping question settled
  first).
- **Out of scope this pass:** full BICEPS state machine, MDS/VMD/Channel
  implementation, any `SdcAdapter/` codegen beyond WS-Discovery — future
  track(s) once the design doc's open question is resolved.
- **Tests:**
  - Unit: WS-Discovery responder answers a multicast probe correctly.
  - Integration: a minimal SDC-aware test harness discovers a
    Harpia-generated endpoint via WS-Discovery and opens the existing
    SOAP/MDPWS-compatible connection.
  - Acceptance gate: existing Stage 11 SOAP tests (14.8/14.9) unaffected.

---

## Definition of done (applies to both tracks above)

- Unit tests for every new construct/behavior introduced.
- Integration test covering end-to-end behavior — for Track P, an actual
  DDS publish/subscribe exchange under the specified QoS, not just unit
  tests of the QoS-mapping logic in isolation.
- Full F4 regression baseline still passes.
- Track P specifically: one-paragraph note added to `ComplianceReport/`
  describing what changed and why (feeds Track M later), same rule
  Session 2 applies to Track C.
- Track Q's design doc is reviewed against
  `harpia_sensitive_data_design_rules.md` before any of its grammar
  hypothesis gets implemented in a later track — don't let the mapping
  guess above ship as fact.

## Watch for

- Track P's DDS-Security config is part of the single project-wide
  `risk_class` floor, same as Track B/C — there's no per-variant parity
  job to feed (Track N's feature-parity diff was dropped entirely per
  `harpia_medical_master_plan.md` §0a; one code path, nothing to diff).
- Don't let Track Q's scoping work quietly turn into implementation
  mid-session — the deliverable is a design doc + WS-Discovery responder,
  not a working BICEPS stack. If the session has spare capacity after
  both, pull from the backlog (`plans/README.md`) rather than scope-creep
  Track Q.
