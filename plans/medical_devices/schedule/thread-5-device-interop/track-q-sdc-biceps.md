# Track Q — IEEE 11073 SDC/BICEPS device-interop bindings (scoping only)

**Explicitly scoped as a design/scoping deliverable this pass, not a full
implementation** — same posture the master plan takes with Track J. IEEE
11073 SDC (ISO/IEEE 11073-10700 series: BICEPS + MDPWS) is a
substantially larger semantic lift than Track P's transport/QoS work — it
defines a whole participant/data model (MDS → VMD → Channel →
Metric/Alert/Context hierarchy), not just a wire protocol.

**Why this leans on Track C's Stage 11 SOAP work rather than starting
cold:** MDPWS (the SDC transport binding) is SOAP-over-HTTP with
WS-Discovery for zero-config peer discovery. Harpia's generator already
emits WSDL + SOAP endpoints (`Database/SoapAdapter.py`,
`Database/WsdlAdapter.py`, Stage 11) gated by the same credential model
Track C is hardening.

## Receives (must be done before this track starts)

- **F1, F2** from Foundation (see `../thread-5-device-interop/README.md`).
- Nothing hard from Track P. **Flag, not a dependency:** this track's
  design work (Q.2 below) benefits from Track P's QoS/delivery-guarantee
  mapping as a worked precedent for how a new transport ties into
  `phi`/`critical` schema-level modifiers — read
  `track-p-dds-transport.md` first if available, but Q.1 (WS-Discovery)
  doesn't need it at all.

## Gives (what "done" means here, consumed by whom)

- A working, standalone WS-Discovery probe/resolve responder, and a
  design doc (`plans/medical_devices/sdc_biceps_design.md`) covering the
  Metric/Alert/Context mapping question — **not** implementation of the
  mapping itself.
- **Consumed by:** no current track — the full BICEPS state machine,
  MDS/VMD/Channel implementation, and any `SdcAdapter/` codegen beyond
  the WS-Discovery responder are explicitly out of scope this pass and
  become their own future track(s) once Q.2's open question is resolved.
  **Flag:** the docs don't name that follow-on track yet — it doesn't
  exist to be a "consumer" of this one today.

## Files this track touches

- `Database/SoapAdapter.py`, `Database/WsdlAdapter.py` — read/layer onto
  the existing SOAP stack, per the master plan's framing ("leans on...
  rather than starting cold"); the docs don't specify whether this track
  modifies these files or only reads their existing behavior as a
  precedent — **flagging that ambiguity rather than guessing which.**
- New `SdcAdapter/` (scoping only this pass, per
  `harpia_medical_master_plan.md` §2's track table).

---

## Session Q.1 — WS-Discovery probe/resolve responder

- **Depends on:** F1 (Foundation). Does not need Q.2 or Track P — fully
  standalone, doesn't require the Metric/Alert/Context mapping question
  settled first.
- **Deliverable:** a working WS-Discovery probe/resolve responder (UDP
  multicast — not currently emitted anywhere in the pipeline), alongside
  the existing SOAP endpoint.
- **Tests:**
  - Unit: WS-Discovery responder answers a multicast probe correctly
    (matches the participant's declared type/scope).
  - Integration: a generic SDC-aware client (or a minimal test harness
    mimicking one) discovers a Harpia-generated endpoint via WS-Discovery
    and successfully opens the existing SOAP/MDPWS-compatible connection.
- **Acceptance gate:** existing Stage 11 SOAP tests (14.8/14.9)
  unaffected — WS-Discovery is additive to the existing SOAP endpoint,
  not a replacement for it.

## Session Q.2 — Metric/Alert/Context mapping design doc

- **Depends on:** F1, F2 (Foundation). Benefits from Track P's QoS
  mapping as a precedent (see Receives above) but doesn't hard-depend on
  it, and doesn't depend on Q.1 either — the two sessions in this track
  are independent of each other.
- **Open question this session exists to answer, not assume:** whether
  the existing access-modifier vocabulary (`stream`, `event[cached/not-
  cached]`, `pull`, `push`, `pushpull`) maps cleanly onto BICEPS's
  Metric/Alert/Context split, or whether that forces a new modifier the
  way `phi`/`critical` were added for their own concerns. A first
  hypothesis — `event` ≈ Metric, `critical event` ≈ Alert (pairs
  naturally with Track P's QoS treatment), Context needs something not
  yet in the grammar — is a **hypothesis to validate with a domain-
  expert/regulatory-affairs pass, not a decision this session makes
  alone.**
- **Deliverable:** `plans/medical_devices/sdc_biceps_design.md` covering
  the mapping question above.
- **Out of scope:** any grammar change implementing the hypothesis; the
  full BICEPS state machine; MDS/VMD/Channel participant model
  implementation; any `SdcAdapter/` codegen beyond Q.1's WS-Discovery
  responder.
- **Tests:** none in the usual sense — this is a design-doc deliverable.
  Reviewed against `harpia_sensitive_data_design_rules.md` before its
  hypothesis is treated as anything more than a hypothesis (see the
  thread README's "Watch for").

## Watch for

- Q.1 and Q.2 can run in either order or in parallel — neither depends
  on the other, unlike most tracks split so far in this restructuring.
- Don't let Q.2 quietly turn into a grammar change or codegen work mid-
  session — its deliverable is the design doc, full stop.
