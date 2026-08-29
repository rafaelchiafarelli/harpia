# Harpia — Design Rules for Sensitive (PHI) Data Handling

Derived from a worked example (heart rate monitoring: `sendHeartRate`). The example is not the rule — it's the instrument that surfaced the rules below. This doc generalizes them so they apply to any sensitive variable Harpia generates code for, not just heart rate.

Status: **working draft** — rules are stated as currently agreed; open questions are marked explicitly and should not be treated as decided.

Examples below are written as `.harpia` DSL snippets, not C++ — this doc describes what gets *declared in the schema*; the C++ that implements each rule is generated from it, once, in the adapters (`Database/`, `ZmqAdapter/`, `Message/toString` templates), not hand-written per message. Modifiers shown as **proposed** (`phi`, `critical`) don't exist in the grammar yet — see `schedule/foundation.md` F2 for `phi`'s planned landing; `critical` (name not final) isn't scoped as an epic yet.

---

## 0. Two independent axes — don't conflate them

Revised 2026-08-18, after a design discussion surfaced that an earlier draft of this doc conflated two unrelated concerns under one word, "sensitive." They are:

- **Confidentiality** — does this *field's value* reveal something private about an identifiable person? This is what `phi` means (Protected Health Information). A heart-rate reading is PHI the moment it's tied to a patient, regardless of how urgently it needs to reach anyone.
- **Criticality** — does *failing to deliver this message*, promptly and completely, cause patient harm? This is a property of a message's role in the clinical workflow (an alarm exists to be acted on immediately), not of any field's content.

A message can be low-criticality/high-confidentiality (routine heart-rate telemetry: private, but a dropped sample is harmless — see Rule 4), or high-criticality and *also* high-confidentiality (a patient-specific alarm). They don't substitute for each other, and neither implies the other.

**Rule: both are schema-level declarations, never derived from runtime content.**

- `phi` is a **field-level** modifier — because one message legitimately mixes private and non-private fields, and tagging the whole message would force an all-or-nothing choice (over-protect fields that never needed it, or under-protect the one that does).
- Criticality is a **message-type-level** modifier — because it's a property of what the message *is for*, decided once, at design time, by the person defining the schema. It is deliberately **not** a field inside the payload (no `bool isCritical;`, no severity value the transport layer inspects to decide how hard to try).

```harpia
// confidentiality: phi is per-field. This message mixes private and
// non-private data on purpose -- device_id isn't PHI, heart_rate is.
event message HeartRateReading {
    phi int heart_rate;
    string device_id;
} table_heart_rate;

// criticality: a dedicated message type for the alarm class of event.
// Every field in it is critical by construction -- there's no "which
// field made this one urgent" question to ask, because the TYPE answers
// it. patient_id here also happens to be phi -- the two tags are
// independent and can both apply to the same schema.
critical event message AlarmEvent {
    phi string patient_id;
    string alarm_type;
    int severity;
} table_alarm_event;
```

**Why not a per-field "critical" tag instead, mirroring `phi`?** That was seriously considered and rejected. It would mean deciding, at runtime, whether *this particular message instance* needs guaranteed delivery by inspecting a value inside it — **content-based execution**. That's the anti-pattern this rule exists to rule out: it makes the delivery guarantee only as trustworthy as the data that triggers it, instead of a fact provable from the schema alone before any instance is ever created. If a real device needs to bundle an alarm-worthy reading alongside routine telemetry in one wire message, the fix is to split it into two message types (one critical, one not) — not to make criticality a value the transport layer has to read and trust.

---

## 1. Reusable delivery/integrity machinery, implemented once in the generator

**Rule:** Sensitive-data handling (redaction, integrity protection, delivery guarantees) is implemented once, in Harpia's code-generation adapters — never re-derived per domain payload type (heart rate, SpO2, blood pressure, ...) by hand.

**Why:** If every new sensor type's generated code re-implements PHI redaction and delivery logic from scratch, a future fix (e.g. a new hazard mitigation) has to be propagated by hand to every generated struct. Harpia has no generics/templates in the `.harpia` grammar itself (there's no `Message<Payload>`-style parametric type) — so "implemented once" means once **in the Python adapters that read the schema's modifiers** (`phi`, `critical`, transport qualifiers) and emit the same protective C++ for every message that carries them, not once as a single reusable DSL declaration.

The `.harpia`-level pattern for a shared envelope is composition — a plain (non-persisted) message with the common transport/integrity fields, embedded by reference in every domain payload that needs them:

```harpia
// shared envelope fields -- composed into any message that needs them,
// not templated. crc/seq are computed at origin (Rule 3) and carried
// unmodified; the adapter that emits (de)serialization code recognizes
// this shape and wires the integrity checks at trust-boundary crossings.
message Envelope {
    int seq;
    int crc;
    string deliveryTimestamp;
}

event message HeartRateReading {
    Envelope envelope;
    phi int heart_rate;
} table_heart_rate;
```

Domain payload fields (`heart_rate`, future `spo2`, etc.) carry no transport, ordering, or integrity logic themselves — that all comes from `Envelope` plus whatever the `phi`/`critical` modifiers trigger in the generated code.

---

## 2. Scope boundary: chain of custody vs. our custody

**Rule:** A function/module is only responsible for hazards it can actually detect or control. Sensor-truth integrity (bad silicon, ADC faults, acquisition-side race conditions) belongs to the acquisition layer's contract, not to the delivery/transmission code. Delivery code is responsible for **integrity of the handoff and the transmission**, not for **truth of the underlying physiological value**.

**Consequence:** No plausibility/range checks on domain values inside message-handling code. If the acquisition layer asserts a value is valid, delivery code trusts that assertion and focuses on not corrupting or losing it in transit.

**Open question:** Whether integrity-check failures at the arrival boundary should be surfaced back to the acquisition layer (not just logged locally), so a systemic transmission problem on their side is visible to them too. Not yet decided.

---

## 3. Integrity checks belong at trust-boundary crossings, not at every internal step

**Rule:** Compute a CRC (or equivalent) **once, at the origin** — the `Envelope.crc` field in Rule 1's shape — and carry it unmodified through the whole lifecycle of the message. Verify it only at genuine trust-boundary crossings:

- **Arrival** — when a message crosses from one module/ownership domain into ours.
- **Departure** — when a message leaves our custody for a different trust domain (network, external system) that cannot rely on our local memory protections.

**Do not** re-verify or recompute CRC between internal steps within the same custody domain (e.g., between a queue push and a queue pop inside the same service) — that is not a hand-off, and re-checking there is redundant cost against a threat already mitigated by hardware.

**Hardware dependency:** If the target hardware has ECC RAM, in-custody bit-flip risk is already mitigated at the hardware level; software CRC at internal steps would be pure redundancy. If the target hardware lacks ECC RAM, this needs re-evaluation — the "no re-check between internal steps" rule assumes ECC coverage for that window. **Confirm target hardware ECC status before applying this rule as-is.**

---

## 4. Delivery guarantee is chosen per message type, not one-size-fits-all

Not every message has the same delivery requirement. Two categories identified so far — and, per Rule 0, the choice belongs on the **message type**, declared in the `.harpia` schema, not inferred from anything inside a message instance.

### 4a. Ordered / complete delivery
Every instance must reach the destination, in order, regardless of transient network unavailability. Used when the receiving system needs a complete historical record (e.g. an audit/compliance trail) — which is also, not coincidentally, usually a message that's worth persisting:

```harpia
critical event message AlarmEvent {
    phi string patient_id;
    string alarm_type;
    int severity;
} table_alarm_event;   // <- persisted: a complete history is exactly the point
```

- Mechanism (generated code): a bounded queue (fixed capacity, sized to the real workload — not arbitrarily deep).
- On overflow: **rotate**, don't silently drop and don't grow unbounded. Track and expose that rotation occurred (don't hide data loss as if it didn't happen).
- Carries `Envelope.seq` for gap detection, `Envelope.deliveryTimestamp` for latency visibility. **Open question, not yet resolved:** whether `deliveryTimestamp` is worth its overhead for every message of this category, or should be added only where downstream consumers actually need latency data. Flagged as possibly excessive — evaluate per use case rather than defaulting it on.
- Failure modes are explicit and auditable: queue full → rotation event logged; never a silent drop.

### 4b. Latest-value-only delivery
Only the current value matters. An unsent value being superseded by a newer one is acceptable and expected — completeness of history is not a requirement, so there's usually no reason to persist every instance either:

```harpia
event message HeartRateReading {
    phi int heart_rate;
    Envelope envelope;
} table_heart_rate;   // persisted here for the *current* reading / phi audit
                       // trail (Rule 0's confidentiality axis), independent
                       // of the fact that history-of-every-sample isn't needed
```

- Mechanism (generated code): a fixed 2-slot mailbox (double-buffer), not a queue. No depth to tune, structurally cannot "overflow" — it overwrites instead.
- On overwrite: log it as an explicit, named event (e.g. `reading_overwritten_pending_delivery`) — an honest failure mode, not a silent one.
- Memory cost is fixed and small (2x payload size) regardless of throughput.

**Rule for choosing between them:** Decided by what the *receiving system* actually needs for that message TYPE — a complete record, or current state. This is a requirement question about the consumer, not a technical preference about the producer, and not something that varies instance-to-instance within one message type. Ask before assuming.

**Explicitly rejected:** Bounded-blocking synchronous send as a general-purpose default. It reintroduces the real-time stall hazard (a slow/unavailable network delays the next sample) regardless of how short the timeout is. Not viable for anything on a real-time sampling path.

---

## 5. What responses to failure must never do

Regardless of delivery policy — this section describes conventions the *generated/consuming C++* must follow, not `.harpia` syntax; there's no schema-level construct for a function's failure-return shape:

- **Never return `void` from an operation that can fail.** Every failure mode (rejected input, integrity failure, queue full/rotated, transmission failed) must be a distinct, observable value in the function's return type — not silently swallowed, not left to an exception the caller might not catch.
- **Never let sensitive-value content leak into logs.** Audit logging captures that an event happened (rejected, sent, failed, rotated, overwritten) and identifying metadata (patient/device ID), never the sensitive value itself. Enforce this by the logging function's signature not accepting the value at all — not by a coding-convention reminder.
- **Never silently correct or clamp an out-of-range or failed-integrity value.** Reject and log; do not guess a "fixed" value and proceed as if it were fine — that hides a real fault behind a plausible-looking success.

---

## 6. Regulatory / jurisdiction note (from earlier discussion, restated generally)

FDA, EU MDR, and ANVISA all converge on the same underlying standards (IEC 62304 for software lifecycle, ISO 14971 for risk management) for software capable of causing serious harm (Class C equivalent). This means:

- **Code and architecture do not need to branch per jurisdiction.** The mitigations above (validated input at the right boundary, explicit failure modes, tamper-evident audit trail, no PHI in logs, criticality decided statically rather than from content) satisfy all three regimes simultaneously, because they derive from the same harmonized standards.
- **What differs per jurisdiction is paperwork, not code**: which document package the hazard/risk table is filed into (DHF vs Technical Documentation vs technical dossier), who reviews it, and post-market reporting obligations if a hazard materializes in the field.
- **One exception worth tracking:** EU MDR's cybersecurity annex (IEC 81001-5-1) is currently more prescriptive about audit-log integrity (tamper-evidence) than FDA/ANVISA. Treating tamper-evident/append-only audit storage as the default everywhere — not gated behind an EU-only flag — satisfies the strictest requirement without needing jurisdiction-specific branches. A `critical` message failing to deliver is itself exactly the kind of event that belongs in that tamper-evident trail, same as a `phi` access.
- **Consequence for the master plan (2026-08-19):** since jurisdictions converge on the same underlying standards, code generation never forks per jurisdiction — there is one hardened profile, not one build variant per FDA/EU MDR/ANVISA. `jurisdiction[]` in `project.harpia.yaml` only selects which paperwork template the process-artifacts epic stamps the same evidence into. See `harpia_medical_master_plan.md` §0a for the full consequence on the Foundation and epic plan.

### 6a. `risk_class` is a project-wide floor; `phi`/`critical` are opt-in on top of it

This is the practical answer to "what happens to an untagged message living next to a `phi`/`critical` one in the same generated project?" — decided 2026-08-19, driven by IEC 62304 §4.3's segregation rule: if a lower-class software item isn't (or can't be proven) segregated from a higher-class item sharing the same binary, the *whole* item is classified at the higher class. A generated project mixing an untagged message with a `phi`/`critical` message on the same transport/process is exactly that unsegregated case.

- **`risk_class`** (project-level, from `ComplianceContext`) sets a floor for the *entire* generated project the moment it implies medical-device-grade: mTLS/RBAC required on every transport, plaintext refused, tamper-evident audit storage present — regardless of which individual messages are tagged `phi`/`critical`. This cannot be per-message; segregating it per-message is exactly the thing IEC 62304 won't credit without real proof of isolation, which Harpia's generated projects don't attempt to provide.
- **`phi`/`critical`** stay genuinely opt-in *above* that floor, for machinery that would be pure waste if forced onto every message: envelope encryption + redaction only on `phi` fields (Rule 1), ordered-delivery queues only on `critical` message types (Rule 4a). Forcing a bounded guaranteed-delivery queue onto routine, non-critical telemetry has a real memory/complexity cost with no corresponding hazard to justify it.
- **No tags anywhere, `risk_class` unset** → today's Harpia output, byte-for-byte (Rule F2's existing guarantee). The hardened floor only activates once a project actually claims medical-device-grade status.

This is not legal/regulatory advice — confirm with actual regulatory affairs expertise before treating this section as sufficient for a real submission.

---

## 7. Open items carried forward (not yet resolved)

- **Grammar for the criticality modifier** — `critical` above is illustrative, not a naming decision. Needs its own scoping pass (parallel to `schedule/foundation.md`'s F2 for `phi`) before either lands in `LexicalAnalizer/`/`Message/`. Worth deciding together, since both are schema-level classification modifiers and might share plumbing (e.g. both could feed `ComplianceContext`/`AuditSink` the same way).
- Whether arrival-integrity failures should be signaled back to the acquisition layer/Harpia side, not just logged locally.
- Whether `deliveryTimestamp` is justified as a default field on every ordered-delivery message, or should be opt-in per use case.
- Exact sizing/capacity for the ordered-delivery queue — should be derived from real workload data (expected message rate vs. expected network downtime tolerance), not picked arbitrarily.
- Retry policy for failed deliveries is intentionally left as external configuration (referenced as "Harpia config" in discussion) rather than embedded in this logic — needs a concrete home/spec once that configuration surface exists.

## 8. Resolved this session (2026-08-18) — kept here for the record

- **"A message is more critical/protected than another" is not the same claim as "a variable is PHI."** These were being used interchangeably early in the design discussion; Rule 0 above is the correction.
- **Content-based execution is rejected as a pattern for criticality.** Delivery-guarantee behavior must be provable from the message *type* declared in the schema, never from inspecting a value inside a message instance at runtime.

## 9. Resolved this session (2026-08-19) — kept here for the record

- **Jurisdiction is not a code-generation axis.** The master plan's earlier "one compile-time build variant per jurisdiction" strategy is dropped; `jurisdiction[]` now only selects the process-artifacts epic's paperwork template. See §6/§6a and `harpia_medical_master_plan.md` §0a.
- **`risk_class` is a project-wide floor, `phi`/`critical` are opt-in on top of it** — not three independent, equally-weighted axes. See §6a, grounded in IEC 62304 §4.3's segregation rule.
