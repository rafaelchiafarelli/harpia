## Metric / Alert / Context mapping design doc

**Done 2026-08-30** — deliverable is
[`../sdc_biceps_design.md`](../sdc_biceps_design.md): the three BICEPS
categories in spec-free detail, a dimension-by-dimension map of the
current modifier vocabulary against them (cadence / cardinality /
validity-state / latching / criticality), the `event ≈ Metric report`,
`critical event ≈ Alert`, `Context ≈ no-grammar-yet` hypothesis stated as
a hypothesis, seven gaps with what-breaks-if-not-added for each, and a
V1–V7 "needs validation by" list (domain-expert / regulatory passes). No
grammar change, no modifier name, no lexer/`Message/` edit — §7 discipline
check included in the doc. No test suite (design deliverable).

Scoped 2026-08-30. **Task 3** of the sdc-biceps epic. A design-doc
deliverable, **not code** — the epic exists to answer this question with a
concrete written design before anyone commits to building the BICEPS data
model. Independent of tasks 1 and 2; can run in parallel with them.

### Contract

- **Depends on:** F1, F2 (Foundation). Benefits from the (now merged)
  dds-transport QoS mapping as a worked precedent for how a new transport /
  vocabulary binding ties into the schema-level `phi` / `critical`
  modifiers — read `../dds-transport-done/tasks/dds-adapter-qos-mapping-done.md`
  first — but has no file dependency on it and does not depend on task 1 or
  task 2.
- **Deliverable:** a new doc `Initiatives/medical_devices/epics/sdc-biceps/sdc_biceps_design.md`
  covering:
  1. The BICEPS Metric / Alert / Context categories, in enough detail that
     the mapping question is legible without the reader owning the 11073
     spec (Metric = periodic value + measurement/validity state; Alert =
     alarm condition + signal, latching/limit semantics; Context =
     rarely-changing patient / location / operator association).
  2. Whether the existing access-modifier vocabulary (`stream`,
     `event[cached/not-cached]`, `pull`, `push`, `pushpull`) maps cleanly
     onto that split, dimension by dimension — cadence, cardinality,
     validity/quality state, latching, criticality.
  3. The starting hypothesis, stated **as a hypothesis, not a decision**:
     `event`-modified message ≈ Metric report; `critical event` ≈ Alert
     (pairs naturally with the dds-transport QoS treatment —
     RELIABLE/KEEP_ALL); Context ≈ a concern with **no current grammar
     representation**, candidate for a new modifier.
  4. For each gap the hypothesis exposes: what a new modifier would have to
     express, and what breaks if it's *not* added (i.e. what a mapping
     forced through the current vocabulary would get wrong).
  5. An explicit "needs validation by" list — which questions require a
     domain-expert / regulatory-affairs pass before any grammar is locked.
- **Out of scope — hard boundary:**
  - Any `.harpia` grammar change implementing the hypothesis.
  - The full BICEPS state machine; MDS / VMD / Channel participant model.
  - Any `SdcAdapter/` codegen beyond task 2's WS-Discovery responder.
  - Any change to `LexicalAnalizer/` or `Message/`.
- **Tests:** none in the usual sense — this is a design-doc deliverable.
  Before its hypothesis is treated as anything more than a hypothesis the
  doc is reviewed against `../../harpia_sensitive_data_design_rules.md` §7
  (the same discipline that doc applies to its own open items — nothing
  inferred, nothing decided implicitly).
- **Done =** `sdc_biceps_design.md` committed **and** this task file marked
  done (the two travel together — commit is the source of truth).

**Watch for.**

- The single biggest failure mode for this task is scope creep into
  implementation. If you find yourself editing the lexer or sketching
  concrete DSL syntax for the "Context" modifier, stop — the deliverable is
  the analysis and the open-questions list, not the modifier.
- Don't re-derive the master plan's device-interop framing from scratch —
  `../README.md` and `../../harpia_medical_master_plan.md` §"sdc-biceps"
  already carry the settled context; this doc extends it, it doesn't
  restate it.
- If open question 9 in the fhir-facade README ("break-the-glass" access
  override) comes up here, it's cross-referenced, not owned by this task —
  leave it to transport-authn / fhir-facade.

---
## Epic context — sdc-biceps

**Contract (this pass — scoping / design deliverable, not full implementation).**
Two concrete outputs: (a) a working, standalone WS-Discovery probe/resolve
responder emitted alongside the existing Stage 11 SOAP endpoint, and (b) a
design doc answering whether the existing access-modifier vocabulary maps onto
BICEPS's Metric/Alert/Context split or forces a new modifier. The full BICEPS
state machine, the MDS/VMD/Channel participant model, and any `SdcAdapter/`
codegen beyond the WS-Discovery responder are **out of scope this pass** and
become follow-on epic(s) once the design doc's open question is resolved.
Needs `ComplianceContext` (F1) and the `phi` field tag (F2) from Foundation.

**Files.** New `SdcAdapter/` (task 2); `UnitTests/` (tasks 1 and 2).
`Database/SoapAdapter.py` and `Database/WsdlAdapter.py` are **read as precedent
only, never modified** (decided during planning 2026-08-30).

**Decided during planning (2026-08-30).**
- The responder advertises a **fixed generic DPWS device type** and a
  **Harpia-namespaced scope URI derived from project + message name** — no
  new `.harpia` modifier this pass (keeps the "design, don't implement
  grammar" posture; pre-empts nothing in task 3's open question).
- The discovery test client is its own task (task 1), done and merged
  before task 2's integration test.

**Open question (task 3 exists to answer, not assume).** Whether `stream` /
`event[cached/not-cached]` / `pull` / `push` / `pushpull` map cleanly onto
BICEPS Metric/Alert/Context, or force a new modifier the way `phi` / `critical`
were added. The `event` ≈ Metric, `critical event` ≈ Alert, Context ≈
not-yet-in-grammar hypothesis is a **hypothesis to validate with a
domain-expert / regulatory-affairs pass** — task 3 does not lock grammar from
it (design-rules §7 discipline).

**Watch for.** Don't let task 3 turn into a grammar change or codegen work —
its deliverable is the design doc, full stop. Don't let task 1 or task 2 turn
into a BICEPS data-model implementation.
