# FHIR Mapping Design — Track R

Status: scoping conversation captured, no grammar/code committed yet.
This is the Track R deliverable referenced in
`harpia_medical_master_plan.md` §5. Nothing here is implemented — every
decision below is either a stated design rule (safe to build against) or
an explicitly flagged open question (needs resolution before grammar is
locked).

---

## 1. Where this sits in the pipeline

FHIR support is a **translation façade added beside the existing
adapters, never a replacement for the `.proto`/gRPC path.**

- `ProtoFile/FileCreator.py`, `ProtoCompiler.py`, `GrpcCompiler.py` are
  untouched. The compiled protobuf message stays Harpia's internal
  source of truth, same as it is today.
- A `FhirAdapter/` reads the already-compiled message's fields plus a new
  mapping annotation and emits `to_fhir()`/`from_fhir()` and a
  `/fhir/...`-scoped REST surface — the same relationship `JsonAdapter`,
  `Database/SoapAdapter.py`, and `Database/RestAdapter.py` already have
  to the compiled message. None of those adapters re-derive the data
  model or duplicate each other's business logic; `FhirAdapter/` follows
  the same pattern.
- `Database/RestAdapter.py` is **read from, not modified** — the generic
  REST endpoint Stage 12 already emits keeps working unchanged; FHIR is
  an additional, separate endpoint for messages that opt in.

## 2. Generation contract: what's generated vs. what's declared

Two different things, kept separate on purpose:

- **The mapping declaration must come from the `.harpia` author.** Which
  FHIR resource a message represents, which field carries which coded
  value, which terminology system applies — Harpia cannot infer this
  from field names or types. Same division of labor as `phi`/`critical`
  today: the user declares intent, Harpia does the mechanical work.
- **Once declared, the generated code must be complete, not a stub.**
  Same guarantee `JsonAdapter`'s `to_json`/`from_json` already give:
  working code the moment the schema compiles, not scaffolding left for
  the user to finish.
- **Unmapped fields are omitted, never fabricated.** Consistent with
  `harpia_sensitive_data_design_rules.md` §5 — Harpia never invents a
  plausible value to make output look complete. (Superseded in part by
  §6 below — "omitted" is now the fallback only when the author didn't
  also opt into the extension mechanism.)
- **Full profile conformance (e.g. a specific implementation guide like
  US Core) is out of scope for the generator to certify** — same
  boundary Harpia already keeps around arbitrary business-rule
  validation today.

## 3. Mapping grammar — two levels, explicit only

- **Message-level annotation:** declares which FHIR resource type the
  message maps to (e.g. `HeartRateReading` → `Observation`).
- **Field-level annotation:** declares where in that resource each field
  lands (e.g. `heart_rate` → `Observation.valueQuantity`, `reading_code`
  → `Observation.code`).
- **No inference from field name or type, ever.** A field named `code`
  or `status` that happens to match a FHIR element name is not
  auto-mapped. This is the same rule that keeps `phi` and `critical`
  explicit rather than name-sniffed, applied consistently here.
- **Declared mappings must satisfy the target element's real
  constraints** — cardinality, datatype, and terminology-binding
  strength (`required`/`extensible`/`preferred`/`example`). "Expected to
  work as described" is a real conformance bar, not a suggestion — this
  is why the acceptance test (§9) requires validating the hand-mapped
  example against a public FHIR validator, not just "looks plausible."
- **`critical`/`phi` don't need new FHIR-specific grammar — they map
  onto existing spec mechanisms (2026-08-21):**
  - `critical` is a delivery-guarantee/QoS concern, already fully
    handled by Track P (DDS `RELIABLE`/`KEEP_ALL` vs.
    `BEST_EFFORT`/`KEEP_LAST(1)`). No FHIR-specific translation needed.
  - `phi` maps directly onto FHIR's native security-labeling mechanism:
    a `phi`-tagged field present in a message → the generated resource's
    `meta.security` gets populated with a code from HL7's standardized
    Confidentiality code system (e.g. `R`/Restricted as the default —
    whether the level itself is a fixed default or an author-chosen
    value per field is a small remaining decision, same shape as the
    already-resolved `modifierExtension` call: author's discretion, not
    a Harpia heuristic).
  - **Terminology-code binding is decided: static.** A compile-time
    literal, consistent with Harpia's existing compile-time-seam pattern
    (F5's `CryptoBackend`, one selection per project driven by
    `risk_class`/`topology`, never per jurisdiction — see
    `harpia_medical_master_plan.md` §0a) and with IEC 62304-style locked
    build artifacts. Consequence to plan for: a LOINC/SNOMED code
    correction means a rebuild, and depending on the device's software
    safety classification, that rebuild likely triggers IEC 62304
    change-control obligations — not a config hot-fix.
  - **New item with no existing Harpia equivalent:** the spec's
    "break-the-glass" security label — emergency clinician override of
    normal access restriction, logged rather than blocked. Nothing in
    `phi`/`critical`/Track C's RBAC models "allow anyway, but log
    loudly" today. Open question, not designed yet.

## 4. FHIR is two-way — this changes CapabilityStatement and read-gating

FHIR is a full REST CRUD surface (`GET`/`POST`/`PUT`/`DELETE`/`PATCH`
per resource type), not a one-directional publish protocol. Two concrete
consequences for Track R:

- **Harpia must generate the server's `CapabilityStatement`
  (`GET /metadata`)** listing *only* the resource types the schema
  actually maps — never implying support for the full ~150-type FHIR
  catalog. A querying client's discovery step has to reflect what was
  actually built, not the spec's theoretical maximum.
- **Read access needs the same RBAC/audit gating Track C already puts on
  writes — not a lesser bar.** Under LGPD (§7 below), reading a
  `phi`-tagged resource is itself an act of "processing" sensitive data,
  same legal-basis question as writing it. `GET /Observation` cannot be
  an open, ungated endpoint just because it's "only a query."

## 5. Extensibility — undeclared fields get a real home, not just omission

FHIR's `extension` mechanism resolves the "what happens to a field with
no standard element" question more completely than "just omit it":

- Every resource/element carries an optional `extension` array:
  `{"url": "<URI>", "value<Type>": ...}`. A consumer that doesn't
  recognize the URL simply ignores it — the resource stays valid.
- **Design rule:** a field with a genuine standard-element mapping goes
  there. A field with no standard home but that doesn't change clinical
  interpretation gets emitted as a Harpia-namespaced `extension`, with
  the generator auto-deriving the URL from message/field name (e.g.
  `https://harpia.dev/fhir/StructureDefinition/{message}-{field}`).
- **`modifierExtension` is explicit-opt-in only, never a default.** It
  signals "a consumer that doesn't understand this must refuse to
  process the resource rather than misinterpret it" — reach for it only
  when omitting the field could produce a clinically wrong reading, and
  only when the schema author deliberately marks it as such.
- **`Resource.meta.security` is a candidate carrier for the `phi`/legal-
  basis metadata** discussed in §7 — a spec-native place for a
  confidentiality label, rather than inventing a custom extension for
  something FHIR already has a slot for. Not decided — flagged as an
  option to evaluate, not a committed design.

## 6. Composition — one message may span several resources

Two native FHIR mechanisms, and the grammar needs to account for both
rather than assuming "one message = one self-contained resource":

- **`Reference`** — resources point at each other by ID
  (`"reference": "Patient/123"`) instead of re-embedding. A composite
  message (e.g. one carrying both a reading and a device identifier)
  should reference an already-emitted resource, not duplicate it inline
  every time.
- **`Bundle`** — groups multiple resources into one atomic
  transaction/submission (e.g. posting a `Device` and its `Observation`
  together).
- **This is a per-message judgment call by the schema author, not a
  default Harpia picks.** The real question per `critical` composite
  message is whether it maps to one resource with several fields, or
  decomposes into several related resources wired together by
  `Reference`, optionally wrapped in a `Bundle`.
- **Decided (2026-08-21): no auto-splitting.** Harpia never detects that
  a group of fields "looks like" enough data to justify a standalone
  companion resource and generates one on its own. If a message needs to
  produce two related resources, the author declares both mappings
  explicitly and wires the `Reference` between them by hand — same
  no-inference discipline as §3.

## 6a. Resource scope — per-device read/write authority, not a fixed allowlist

**Revised (2026-08-21).** The original framing — "`Observation`/
`DeviceMetric` in scope, `Patient`/`MedicationRequest` out" — was too
blunt. Pushback surfaced a real case it excluded: a medication
dispensing cabinet, smart pill dispenser, or automated infusion
controller is a legitimate medical device, and all of them legitimately
touch `MedicationRequest`.

**The actual axis is role within the clinical workflow, not resource
type:**
- A vitals monitor never touches `MedicationRequest` — not applicable.
- A dispensing device needs to **read** `MedicationRequest` ("what's
  currently ordered for this patient") but must not **write** it —
  authoring prescriptions is the prescriber's EHR's job; a dispenser
  doing so would be a genuine safety failure, not a scope violation.
- A dispensing device *should* **write** `MedicationDispense` and/or
  `MedicationAdministration` — recording what the device actually did is
  exactly its role.

**Design implication:** first-pass scope should not be a fixed
resource-type allowlist at all. It should be **per-resource read/write
authority, declared per device category**, expressed through the same
mechanism §"Read-side RBAC" below already needs — SMART on FHIR's
`resource-type.operation` scope granularity (e.g. a dispenser's façade
would plausibly get `MedicationRequest.read` +
`MedicationDispense.write`/`MedicationAdministration.write`, never
`MedicationRequest.write`).

**`Patient` remains reference-only regardless of device category** — the
identity/MRN-matching reasoning in §1 (an MPI's job, not a device's)
doesn't change based on what kind of device is asking.

## 7. Cross-message PHI identity linkage

**The problem:** two `critical` messages can independently declare a
field with the same name (e.g. `patient_id`) with **zero linkage in
Harpia today** — `LexicalAnalizer/MessageCreator.py`'s `allUnique()`
only enforces uniqueness of *message* names; nothing checks or connects
field names across messages. That's fine for the existing DB/gRPC/ZMQ
generation path (no shared namespace, no collision possible). It becomes
a real data-integrity risk the moment FHIR enters the picture, because
FHIR resources have durable server-side identity: if both messages
refer to the same real patient and each independently `POST`s a new
`Patient`, you get two divergent resources for one real person.

- **Hard rule: no name-based auto-linking.** Two fields sharing a name
  is not evidence of shared identity — could be coincidence, could be a
  bug, could be two genuinely different concepts (an internal record key
  vs. a hospital MRN). Auto-linking by name match is exactly the kind of
  inference §3 already forbids for the mapping itself; the same
  discipline applies to identity.
- **Mechanism: FHIR's native `identifier` element**
  (`system` URI + `value`), distinct from the server-assigned `id`,
  designed precisely for "this corresponds to an external record you
  already know by this key." FHIR servers natively support conditional
  create (`POST /Patient?identifier=system|value` → find-or-create).
- **Design:** the `.harpia` author explicitly tags a shared identity key
  on both fields (e.g. an `identity: "patient"` modifier value) —
  deliberate declaration, never inferred. Harpia mints one stable
  `identifier.system` URI per declared key and emits it consistently
  everywhere that key is used. **Resolution of "is this actually the
  same patient" happens at the FHIR server via conditional
  create/match on `identifier`** — Harpia's generator stays stateless
  per message compile; it does not need to track cross-message runtime
  state itself.
- **Scope decided (2026-08-21): per-project.** Cross-project reuse of
  the same identity key meaning different things is the user's
  responsibility — Harpia has no cross-project registry to check
  against, and won't. One thing Harpia gives for free at no extra
  design cost: mint the `identifier.system` URI with the project's own
  identifier baked in (e.g.
  `https://harpia.dev/fhir/identifier/{project}/patient`), so two
  different projects can't collide on the URI even by accident. This
  doesn't stop misuse of a key *within* one project — that stays a
  human/review problem — but it removes accidental cross-project
  collision as a failure mode entirely.

## 8. LGPD intersection (Brazil) — not a resource-type question

No FHIR resource type is itself incompatible with LGPD — the law doesn't
ban any data structure. The constraint attaches to **legal basis and data
flow**, not schema shape. Not legal advice; needs real counsel/DPO
sign-off before commit.

- Any resource carrying health data (`Observation`, `DeviceMetric`,
  `Condition`, `MedicationRequest`, a `Patient` linked to health info) is
  automatically "dado sensível" (LGPD Art. 5º, II).
- Processing requires one of exactly two paths (Art. 11), and the
  no-consent path is a **closed list — numerus clausus, no extension by
  analogy**:
  - explicit, specific consent (11-I), or
  - a named exception without consent (11-II) — most relevant here,
    **alínea f: "tutela da saúde, exclusivamente, em procedimento
    realizado por profissionais de saúde, serviços de saúde ou
    autoridade sanitária."**
- **Art. 11 §4 is the sharp edge for this track specifically:** sharing
  health-related sensitive data *between controllers* for economic
  advantage is explicitly forbidden, with narrow carve-outs (health
  insurance, pharmacy assistance, diagnosis/therapy support) under
  further conditions in §5. This is exactly the pattern a FHIR export
  reaching a third-party commercial system (e.g. a device vendor's cloud
  analytics platform) would trigger.
- **§4 implication (from §4 above):** reading a `phi`-tagged FHIR
  resource is processing too — the RBAC/audit gate applies to `GET`, not
  only to writes.
- **Design requirement, revised (2026-08-21) — reuse spec machinery,
  don't invent parallel machinery:** FHIR already has three purpose-built
  resources for exactly this, checked directly against the spec:
  - **`Consent`** — records a patient's consent preferences and scopes
    permission to specific purposes/recipients. This can directly carry
    the LGPD legal-basis declaration instead of a custom field.
  - **`Provenance`** — records who initiated a create/update and the
    context data was obtained in.
  - **`AuditEvent`** — records access events, carrying a `purposeOfUse`
    element for why a person/machine/software participated. This maps
    directly onto Harpia's existing `AuditSink` concept from the
    compliance tracks (F3) — likely the same hook, not a second one.
  - **Real limitation, not a design gap to solve — a spec ceiling:** all
    three of these operate at **resource level, not field level**.
    `Consent.provision`, `Provenance.target`, and `AuditEvent.entity` all
    reference whole resources, never individual elements within one.
    Harpia's `phi` modifier is field-level today. Consequence: if even
    one field in a message is `phi`, the *entire* generated resource
    inherits `Consent`/audit treatment — there's no FHIR-native way to
    get "only `patient_id` was accessed, not `heart_rate`," within one
    `Observation`. State this as a known limitation in any future
    implementation, don't try to engineer around it.

## 9. Tests (design-validation phase, not generated code)

- The hand-mapped `Observation` example (from `HeartRateReading` in
  `harpia_sensitive_data_design_rules.md`) validates against HL7's
  published FHIR resource schema via a public FHIR validator — proves
  the target shape is reachable before any codegen is built.
- No acceptance gate yet for this pass — produces a doc + one manual
  example; the real acceptance gate belongs to the follow-on
  implementation track.

## 10. Explicitly out of scope this pass

- Any generated `FhirAdapter/` code.
- `Bundle`/transaction semantics, `Reference` resolution logic.
- FHIR search-parameter query support.
- The `CapabilityStatement` endpoint itself (design only — §4 states the
  requirement, doesn't build it).
- Full implementation-guide/profile conformance certification.
- The `identifier`-based identity-linkage mechanism's actual grammar
  syntax (§7 states the mechanism, doesn't lock the DSL syntax).

---

## Open questions to investigate

These are the items this doc deliberately leaves unresolved. Each needs
a decision — domain-expert, legal, or architectural — before the
corresponding piece of grammar gets locked in. **Resolved items are kept
here, marked closed, so the reasoning isn't lost.**

1. ~~Terminology-code binding: static or dynamic?~~ **Closed
   (2026-08-21): static.** Compile-time literal, consistent with
   Harpia's existing compile-time-seam pattern (F5's `CryptoBackend`,
   driven by `risk_class`/`topology`, never per jurisdiction — see
   `harpia_medical_master_plan.md` §0a). Consequence unchanged: a code
   correction means a rebuild, likely triggering IEC 62304 change control
   depending on safety classification. (§3)
2. ~~Resource scope for a first pass.~~ **Revised (2026-08-21) — not a
   fixed allowlist.** The axis is per-device-category read/write
   authority, not resource type: a dispensing device legitimately reads
   `MedicationRequest` and writes `MedicationDispense`/
   `MedicationAdministration`, but must never write
   `MedicationRequest` itself. `Patient` stays reference-only regardless
   of device category (MPI/identity-matching reasoning, unaffected by
   device role). Still open: the full per-device-category
   read/write matrix hasn't been drawn up — needs one pass per device
   class Harpia targets before Track R's implementation phase. (§6a)
3. ~~`meta.security` vs. custom extension for `phi` metadata.~~ **Closed
   (2026-08-21): `meta.security`, confirmed against the spec.** FHIR's
   Confidentiality code system is the native, spec-intended mechanism —
   conformant recipients are obligated to enforce and forward it, which
   a custom extension wouldn't get for free. Remaining small decision:
   fixed default confidentiality code (e.g. always `R`) vs.
   author-chosen per field — low-stakes, can be decided alongside
   implementation. (§3)
4. ~~`modifierExtension` criteria.~~ **Closed (2026-08-21): schema
   author's call per field, no Harpia-defined heuristic.** (§5)
5. ~~Composition default.~~ **Closed (2026-08-21): no auto-splitting,
   ever.** Author explicitly declares every resource a message produces
   and wires `Reference`s by hand. (§6)
6. ~~`identifier.system` minting scheme.~~ **Closed (2026-08-21):
   per-project, with the project identifier baked into the minted URI**
   so different projects can't collide even accidentally. Misuse of a
   key *within* one project stays a human/review responsibility — no
   technical safeguard against that, by design (Harpia has no
   cross-project registry). (§7)
7. **Legal-basis/recipient declaration grammar — narrowed, not closed.**
   Revised (2026-08-21): don't design new grammar — map onto FHIR's
   existing `Consent`/`Provenance`/`AuditEvent` resources instead, which
   already cover purpose/recipient/access-event tracking natively.
   Remaining open items: (a) how `Consent`/`AuditEvent` generation
   attaches to Harpia's `AuditSink` hook from F3 — same hook or a
   second one; (b) **the field-vs-resource granularity limit is a real
   spec ceiling, not solvable by better design** — `Consent`,
   `Provenance`, and `AuditEvent` all operate at whole-resource
   granularity, never per-field, so a `phi` field anywhere in a message
   pulls the entire generated resource into `Consent`/audit scope.
   Still needs LGPD counsel/DPO input before any of this becomes DSL
   syntax. (§8)
8. **Read-side RBAC granularity — narrowed, not closed.** Revised
   (2026-08-21): don't invent a new granularity model — adopt SMART on
   FHIR's `(patient|user)/resource-type.operation` scope pattern (and
   SMART v2's finer create/read/update/delete split), which is already
   the de facto spec-adjacent standard and meaningfully finer than
   Track C's three roles. Still open: how SMART scopes get generated
   from `.harpia` declarations, and how they interact with Track C's
   existing admin/main/guest model rather than replacing it outright.
   (§4, §6a, §8)
9. **New (2026-08-21): "break-the-glass" access override.** FHIR's
   security-label spec defines this natively — emergency clinician
   override of normal access restriction, logged rather than blocked.
   No equivalent exists anywhere in Harpia today (`phi`, `critical`,
   Track C's RBAC). Not designed at all yet — needs its own scoping
   pass, likely alongside Track C rather than as pure Track R scope,
   since it's a general access-control concept FHIR just happens to
   name first. (§3)

