# Metric / Alert / Context mapping — design doc

**Task 3 of the sdc-biceps epic.** Scoped 2026-08-30, written 2026-08-30.
A design deliverable, **not code**. It answers one question:

> Does Harpia's existing access-modifier vocabulary (`stream`, `pull`,
> `push`, `pushpull`, `event[cached/not-cached]`, plus the independent
> `critical` axis) map cleanly onto BICEPS's Metric / Alert / Context
> split, or does the split force a new modifier the way `phi` and
> `critical` were forced by their own concerns?

Framing is already settled in [`README.md`](README.md) and
[`../../harpia_medical_master_plan.md`](../../harpia_medical_master_plan.md)
§"sdc-biceps" — this doc extends it, it does not restate it. The
schema-level modifier discipline it works under is
[`../../harpia_sensitive_data_design_rules.md`](../../harpia_sensitive_data_design_rules.md)
§0 (two independent axes, never derived from runtime content), §2 (custody
boundary), §4 (delivery guarantee per message type), §6 (one hardened
profile), and especially §7 (open items stay open — nothing inferred,
nothing decided implicitly). The
[dds-transport QoS mapping](../dds-transport-done/tasks/dds-adapter-qos-mapping-done.md)
is the worked precedent for how a new transport/vocabulary binding ties
into `phi`/`critical`; it is read as precedent only.

**Hard boundary for this doc:** no `.harpia` grammar change, no modifier
name, no grammar production, no default selection. The BICEPS state
machine and the MDS/VMD/Channel participant model are a follow-on epic.
Per §7 discipline, every candidate below is stated as a hypothesis or an
open question — the follow-on epic plus a domain-expert / regulatory pass
own the decisions.

---

## 1. BICEPS Metric / Alert / Context, in enough detail to make the mapping legible

IEEE 11073 SDC's data model is the **MDIB** (Medical Device Information
Base), split into a *descriptive* part (the rarely-changing containment
tree MDS → VMD → Channel → Metric / AlertSystem / SCO, plus descriptors)
and a *state* part (a dynamic state object per descriptor). Values reach
consumers over MDPWS as WS-Eventing reports: `EpisodicMetricReport` /
`EpisodicAlertReport` / `EpisodicContextReport` (fired on change) and
their `Periodic*` counterparts (batched on a timer), plus `WaveformStream`
for real-time sample arrays. The three leaf categories this task is about:

### 1a. Metric — a periodic value plus its measurement/validity state

A single measured, set, or calculated quantity. Subtypes: `NumericMetric`,
`StringMetric`, `EnumStringMetric`, `RealTimeSampleArrayMetric`
(waveforms), `DistributionSampleArrayMetric`.

- **Descriptor** carries: unit (UCUM-coded), `MetricCategory` (`Msrmt`
  measured / `Set` setting / `Clc` calculated / …), `MetricAvailability`
  (`Cont` continuous / `Intr` intermittent), determination period, max
  delay time, lifetime period.
- **State / value** carries a mandatory `MetricQuality` sidecar on *every*
  value: `Validity` ∈ {`Vld` valid, `Vldated` validated, `Ong` ongoing,
  `Qst` questionable, `Calib` calibrating, `Inv` invalid, `Oflw`/`Uflw`
  over/underflow, `NA`}; `Mode` ∈ {`Real`, `Test`, `Demo`}; `Qi` quality
  indicator 0..1. Plus `DeterminationTime`, `ActivationState` ∈ {`On`,
  `NotRdy`, `StndBy`, `Off`, `Shtdn`, `Fail`}.
- **Cadence:** continuous (waveform), periodic, or episodic-on-change.
- **Cardinality:** exactly one current value per metric.
- **A BICEPS consumer is required to suppress or visually flag any value
  whose `Validity` is not `Vld`/`Vldated`, and to flag `Demo`/`Test`
  mode.** The quality sidecar is not optional metadata.

### 1b. Alert — an alarm condition plus its signal(s), with latching/limit semantics

- **`AlertCondition`** — a monitored condition. `Kind` ∈ {`Phy`
  physiological, `Tech` technical}; `Priority` ∈ {`None`, `Lo`, `Me`,
  `Hi`}; `DefaultConditionGenerationDelay` (debounce — the condition must
  persist this long before it counts); `Source` = handles of the metrics
  that feed it. State carries `Presence` (bool — is the condition met
  *now*), `ActualPriority`, `Rank`, `DeterminationTime`.
  `LimitAlertCondition` adds settable upper/lower `Thresholds` and
  `MonitoredAlertLimits`.
- **`AlertSignal`** — the annunciation of a condition. `Manifestation` ∈
  {`Aud` audible, `Vis` visible, `Tan` tangible, `Oth`}; **`Latching`**
  (bool); `AcknowledgementSupported`; `DefaultSignalGenerationDelay`.
  State carries `Presence` ∈ {`On`, `Off`, `Latched`, `Ack`}, `Location`
  ∈ {`Loc`, `Rem`}.
- **One condition drives one-or-more signals** (audible + visible for the
  same alarm), each with its own independent presence/ack lifecycle. An
  alert is a small graph — condition ⟷ N signals ⟷ source metrics — not a
  flat record.
- **Latching semantics:** a latched signal stays in `Latched` presence
  *after* the physiological condition clears, until a clinician
  acknowledges (`Ack`). This is what stops a 400 ms alarm burst from being
  missed. It is a retention/visibility obligation, not just a
  delivery-once guarantee.
- **Cadence:** episodic-on-change. **Criticality:** inherently
  ordered/complete (design-rules §4a) and belongs in the tamper-evident
  audit trail (§6).

### 1c. Context — a rarely-changing patient / location / operator association

- Subtypes: `PatientContext` (demographics — given/family name, birth
  date, sex, height, weight, race → **PHI-dense**), `LocationContext`
  (facility / building / floor / point-of-care / room / bed),
  `OperatorContext`, `EnsembleContext` (which devices act as one set),
  `WorkflowContext`, `MeansContext`.
- **`ContextAssociation`** ∈ {`No` not associated, `Pre` tentative /
  pre-association, `Assoc` associated, `Dis` disassociated}, plus
  `BindingStartTime` / `BindingEndTime` and coded `Identification` /
  `Validator`.
- **Cardinality — the distinguishing feature:** context states are the
  *only* BICEPS states that are legitimately **multi-instance** per
  descriptor. A `PatientContextDescriptor` can carry several
  `PatientContextState` objects at once: the just-left patient in `Dis`,
  the current patient in `Assoc`, an incoming patient in `Pre`.
- **Cadence:** episodic and rare (admit / discharge / bed move). But a
  missed context change silently re-frames the meaning of every metric and
  every alarm underneath it — "whose heart rate is this?" — so delivery
  must be reliable/complete, and a fresh consumer must be able to fetch
  the current set immediately (`GetContextStates`).

---

## 2. Does the current vocabulary map — dimension by dimension

Harpia's modifiers, per design-rules §0 / §6a, are **separate axes**:
transport-role (`stream` / `pull` / `push` / `pushpull` / `event`),
criticality (`critical`), transport-selection (`dds`), confidentiality
(`phi`, field-level). `event` is an on-change publish/subscribe channel;
`event[cached]` replays the last value to a new subscriber,
`event[not-cached]` does not (see
[`../events-callbacks-done/tasks/event-cache-implementation-done.md`](../events-callbacks-done/tasks/event-cache-implementation-done.md)).

| Dimension | Metric | Alert | Context | Covered by current vocabulary? |
|---|---|---|---|---|
| **Cadence** | continuous / periodic / episodic | episodic-on-change + generation delay (debounce) | episodic, rare | **Partial.** `stream` ≈ waveform; `event` ≈ `EpisodicMetricReport` / `EpisodicAlertReport` / `EpisodicContextReport`. No expression of `Periodic*Report` batching, and none of alert **generation delay** (adjacent to the DDS `deadline[ms]` open question, not the same thing). |
| **Cardinality** | one current value | condition + N independently-living signals | **multi-instance** association states | **No** for Alert sub-structure and **No** for Context multi-instance. Harpia messages are single-instance; `repeteable` is a list-field modifier, not "N concurrently-associated context states over the wire." |
| **Validity / quality state** | mandatory `MetricQuality` sidecar on every value | `Presence` bool + `ActualPriority` + `Rank` | `ContextAssociation` enum + binding times | **No modifier.** These can be carried as explicit composed fields (§1's `Envelope` pattern), but nothing at schema level *marks* a message as "a measured quantity that must carry quality metadata" or "an association with a lifecycle state." |
| **Latching** | n/a | `Latching` + `Presence=Latched` + `Ack` | n/a | **No.** `critical` (KEEP_ALL, rotate-don't-drop, audit-on-failure) guarantees *arrival*, not acknowledgement-gated *retention*. And whether latching is even Harpia's concern vs. the consumer's is unresolved. |
| **Criticality** | usually latest-value-only (§4b); a calc metric feeding an alarm may want reliable | inherently `critical` (§4a) | not an alarm, but delivery must be reliable/complete | **Partial.** `critical event` ≈ Alert is the strongest fit. But BICEPS `Priority` ∈ {Lo, Me, Hi} is finer than binary `critical`, and Context wants `critical`-style delivery *without* alarm/audit semantics — see gap 6 and 7. |

**Verdict:** `event` and `critical event` cover **Metric-report and
Alert-report cadence and criticality** well. They do **not** cover
Context's multi-instance association lifecycle, Metric quality state,
Alert sub-structure, or latching. The split does not map cleanly through
the current vocabulary as-is.

---

## 3. Starting hypothesis (a hypothesis, not a decision — §7)

- `event`-modified message ≈ **BICEPS Metric report** (`EpisodicMetricReport`);
  `stream`-modified message ≈ **`RealTimeSampleArrayMetric` / `WaveformStream`**.
- `critical event`-modified message ≈ **BICEPS Alert report**
  (`EpisodicAlertReport`) — pairs naturally with the dds-transport QoS
  treatment (`RELIABILITY=RELIABLE`, `HISTORY=KEEP_ALL`, bounded via
  `resource_limits`).
- **Context ≈ a concern with no current grammar representation** — a
  candidate for a new modifier. Working name deliberately **not** chosen
  here (§7; the "don't sketch DSL syntax" rule in the task file).

This is the master-plan first guess, carried forward unchanged. It is a
hypothesis to validate, not a contract.

---

## 4. Gaps the hypothesis exposes

For each: **what a new modifier (or composed envelope) would have to
express**, and **what breaks if it is forced through the current
vocabulary instead**.

1. **Context association lifecycle + multi-instance cardinality.**
   *Would have to express:* this message type is an *association*, not a
   measurement; it can have several concurrently-live instances each in a
   `ContextAssociation` state (`No`/`Pre`/`Assoc`/`Dis`) with binding
   times; delivery is reliable/complete; a fresh consumer gets the current
   set immediately (cached-like).
   *What breaks without it:* forcing Context through `event[cached]`
   collapses the multi-instance concept — a consumer cannot distinguish
   "patient A `Dis`, patient B `Pre`" from "patient atomically changed
   A→B", cannot represent the tentative `Pre` state at all, and cannot
   re-associate a stream of already-received metrics. Concrete failure:
   a vitals reading filed under the wrong patient — a patient-safety
   *and* a confidentiality failure at once.

2. **Metric quality / validity sidecar.**
   *Would have to express:* "this is a measured quantity; every value
   carries `Validity` + `Mode` + measurement state." Could be a modifier,
   or a §1-style required composed `MetricQuality` envelope — but today it
   is neither, so it is not a schema-level fact.
   *What breaks without it:* a consumer receiving a Harpia-over-SDC metric
   sees a bare number with no way to know it is `Inv` (sensor
   disconnected), `Calib` (mid-calibration), or `Demo` (test mode). BICEPS
   consumers are *required* to suppress/flag non-`Vld` values; a bridge
   that cannot carry the flag presents calibration noise as a real
   reading. Note the §2 boundary: Harpia does not *judge* validity (that
   is the acquisition layer's contract), but SDC requires it to *carry*
   validity — that carriage is the new obligation.

3. **Alert sub-structure: condition ⟷ signals ⟷ sources with independent
   presence and generation delay.**
   *Would have to express:* an alert is a small graph whose parts have
   independent lifecycles (condition present while its audible signal is
   `Ack` but its visible signal is `On`), plus the debounce delay before
   annunciation.
   *What breaks without it:* modelling an alert as one flat
   `critical event` message collapses per-signal acknowledgement state —
   the consumer cannot drive "audible alarm silenced, condition still
   active," which is a mandated clinical interaction.

4. **Latching / acknowledgement-gated retention.**
   *Would have to express:* "hold this state as delivered/visible until a
   consumer acknowledges, even after the underlying condition clears."
   *What breaks without it:* `critical`'s `KEEP_ALL` proves the message
   *arrived*; it does not keep a 400 ms alarm burst on the consumer's
   surface until a clinician sees it — which is the entire point of
   latching. **Open even at the boundary:** whether this is Harpia's job
   or the SdcAdapter runtime's / the consumer's.

5. **Periodic (batched) vs. episodic (on-change) reporting.**
   *Would have to express:* a batching cadence, so a consumer on a slow
   WAN can ask for `PeriodicMetricReport`-style bundling.
   *What breaks without it:* no bandwidth-friendly mode for tele-ICU-class
   links. Likely a transport-tuning concern that can stay out of the
   grammar — flagged **low priority**, listed for completeness.

6. **Graduated alert priority.**
   *Would have to express:* `Priority` ∈ {`Lo`, `Me`, `Hi`} instead of
   binary `critical` — plausibly a parameterised modifier (shape like
   `event[cached]`) *iff* priority is a static property of the alert
   *type*.
   *What breaks without it:* every Harpia-originated alarm annunciates at
   one escalation level — "cuff needs re-zeroing" and "VF detected" are
   treated alike. **Do not lock:** §0's content-based-execution
   prohibition means this only works if priority never varies per
   instance; that needs domain confirmation (§5 below).

7. **`critical` conflates "reliable delivery" with "alarm-class
   audit/latch semantics."**
   Context (gap 1) needs reliable ordered delivery but is *not* an alarm
   and does not want alarm-latch behaviour. Alert wants both. This doc
   **flags, does not resolve**, whether the eventual grammar separates a
   pure delivery-guarantee modifier from an alarm-semantics modifier, or
   layers one on the other.

---

## 5. Needs validation by — before any grammar is locked

Each item names the pass that has to answer it. None is answerable inside
this epic.

| # | Question | Needs |
|---|---|---|
| V1 | Are alert **priority** (`Lo`/`Me`/`Hi`) and **kind** (`Phy`/`Tech`) static properties of a message *type* (safe as modifier parameters) or can they vary per instance (then they are payload data, and §0 forbids the transport reading them)? | Clinical / IEEE 11073 SME |
| V2 | Is **latching / acknowledgement retention** in Harpia's scope at all, or entirely a consumer / SdcAdapter-runtime concern? | Clinical workflow + architecture |
| V3 | Must Harpia **carry** `MetricQuality`/`Validity`, or may it require the acquisition layer to gate invalid values before they reach a Harpia message (the §2 custody boundary)? | Risk management (ISO 14971) + 11073 SME |
| V4 | Is `No`/`Pre`/`Assoc`/`Dis` the full `ContextAssociation` set a Harpia bridge must represent, and is `Pre` (tentative) mandatory for the target device classes? | IEEE 11073 SME |
| V5 | Is **`PeriodicMetricReport` batching** a required interop feature for the intended deployment (bedside LAN vs. tele-ICU WAN), or deferrable? | Deployment / systems engineering |
| V6 | Can a Harpia-generated SDC participant that *carries but does not validate* `MetricQuality` be classed as an "SDC Provider" for submission, or is it a gateway/bridge with a different evidence burden under IEC 62304 + the 11073-10700 series conformance? | Regulatory affairs |
| V7 | Do the §6 tamper-evident audit obligations extend to **context association changes** and **alert acknowledgements**, not only `phi` access and `critical` delivery failure? | Regulatory affairs |

**Cross-reference, not owned here:** the fhir-facade README open question 9
("break-the-glass" emergency access override) can surface when a Context
association is force-changed under duress — that stays with
transport-authn / fhir-facade, not this task.

---

## 6. §7 discipline check

Nothing above selects a modifier name, a grammar production, a default, or
a lexer/`Message/` change. Section 3 is labelled a hypothesis; sections 4
and 5 are gaps and open questions. The follow-on BICEPS epic — which does
not exist yet and is not named here — plus the V1–V7 passes own every
decision. This doc's deliverable is the analysis and the list, per the
task contract.
