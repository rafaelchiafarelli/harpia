## Worked example: `HeartRateReading` -> FHIR `Observation`

Scoped 2026-08-30. **The only task** of the fhir-facade epic — the design
doc (`../README.md`) is already written; this is the one thing it flags as
"not yet done — next concrete step." Proof-of-mapping, no code.

### Contract

- **Depends on:** F1, F2 (Foundation). Independent of every other epic —
  benefits from the sdc-biceps `sdc_biceps_design.md` mapping precedent
  (schema field -> external standard vocabulary) but has no dependency on
  it.
- **Pre-work (done during planning, 2026-08-30):** the FHIR **R4 (4.0.1)**
  JSON Schema is vendored at
  `../worked-example/fhir.schema.json` (+ `VENDORED.md`), mirroring
  `ComplianceReport/schema/bom-1.5.schema.json`. No further fetch/setup
  needed.
- **Deliverable — all under `../worked-example/`:**
  1. `heartrate_observation.example.json` — the `HeartRateReading` message
     (`phi int heart_rate; string device_id;`, the canonical form from
     `../../../harpia_sensitive_data_design_rules.md` §0) mapped **by
     hand** to a conformant FHIR R4 `Observation`:
     - `code` -> LOINC **`8867-4`** ("Heart rate"), `system`
       `http://loinc.org`.
     - `valueQuantity` -> `heart_rate`, UCUM unit `/min` (`system`
       `http://unitsofmeasure.org`).
     - `category` -> `vital-signs`
       (`http://terminology.hl7.org/CodeSystem/observation-category`).
     - `status` -> `final` (FHIR requires it 1..1 even though the JSON
       schema is lenient).
     - `phi` on any field -> whole-resource confidentiality:
       `meta.security` = `R` / restricted
       (`http://terminology.hl7.org/CodeSystem/v3-Confidentiality`), per
       design doc §3 + the §8 "field-level `phi` pulls the entire
       resource into scope" spec ceiling.
     - `device_id` -> `Observation.device` as a **Reference by
       `identifier`** (no separate `Device` resource — respects design
       doc §6 "no auto-splitting"); the `identifier.system` URI is
       Harpia-namespaced with the project baked in
       (`https://harpia.dev/fhir/identifier/<project>/device`), per §7.
  2. `mapping-notes.md` — a field -> element table, each mapping decision
     justified against a numbered design-doc rule, plus an explicit
     **known-gaps** list (e.g. no `subject`/`Patient` reference — the
     `HeartRateReading` form used here carries no patient id; that's a
     real gap the example surfaces, not something to invent per §5 /
     Rule 5).
- **Test:** `UnitTests/test_fhir_observation_example.py` — pure Python,
  always runs, stdlib only (no `jsonschema` dep, same as
  `test_sbom_emission.py`):
  - the example parses and `resourceType == "Observation"`;
  - every top-level key of the example is a declared property of
    `definitions.Observation` in the vendored schema, and the schema's
    `Observation.required` (`code`, `resourceType`) are all present;
  - the clinical content is right: LOINC `8867-4` under
    `http://loinc.org`; `valueQuantity` with UCUM `/min`; `category`
    `vital-signs`; `status == "final"`;
  - `meta.security` carries the `v3-Confidentiality` `R` code (the `phi`
    obligation);
  - `device.identifier.system` is the project-namespaced Harpia URI and
    there is no inline `contained` `Device` resource.
- **Out of scope — hard boundary (design doc §9):** any generated
  `FhirAdapter/` code; any `.harpia` grammar; `Bundle` / `Reference`
  resolution logic; FHIR search parameters; the `CapabilityStatement`
  endpoint; the `identifier`-linkage DSL syntax; profile/IG conformance
  certification. The design doc's open questions (LGPD counsel sign-off,
  SMART-on-FHIR scope generation, "break-the-glass") are **not** closed
  here.
- **Acceptance gate:** none — this pass produces a worked example, not
  shipped code. The real gate belongs to the follow-on implementation
  epic.
- **Done =** the three `worked-example/` artifacts + the test committed,
  full Docker suite still green, and this task file marked done.

**Watch for.**

- Do not let this turn into grammar design or `FhirAdapter/` codegen — the
  deliverable is proof-of-mapping, full stop (same discipline sdc-biceps
  held on its own scoping tasks).
- Do not invent a `subject`/`Patient` reference or any other field the
  `HeartRateReading` message doesn't carry — an omitted element is the
  correct outcome (design-rules Rule 5 / design doc §2), and the gap gets
  recorded in `mapping-notes.md`, not papered over.
- `device_id` is a bare string, not a resource id — `Observation.device`
  is `Reference(Device|DeviceMetric)`. Reference-by-`identifier` is the
  mapping that avoids minting a `Device` resource; don't emit a
  `contained` Device instead.
- If the transport-authn epic picks up design-doc open question 9
  ("break-the-glass") first, update `../README.md` rather than let the
  two drift.

---
## Epic context — fhir-facade

**Contract (this pass — design / scoping deliverable, not implementation).**
The design doc in `../README.md` (merged from the former
`fhir_mapping_design.md`) is complete: FHIR support is a translation façade
beside the existing adapters (`FhirAdapter/` reads the compiled message +
an explicit mapping annotation, emits `to_fhir()`/`from_fhir()` and a
`/fhir/...` REST surface), never touching `ProtoFile/` / `ProtoCompiler` /
`GrpcCompiler` / `Database/RestAdapter.py`. `phi` -> `meta.security`
Confidentiality; `critical` needs no FHIR-specific grammar; terminology
binding is compile-time static. **The one remaining deliverable is the
hand-mapped worked example** (this task) — proof the mapping is expressible
from Harpia's data model before any of it becomes a grammar feature.

**Files.** None in the generator tree this pass. New artifacts live under
`epics/fhir-facade-done/worked-example/` (vendored FHIR R4 schema + the example
+ notes) and `UnitTests/test_fhir_observation_example.py`.

**Decided during planning (2026-08-30).**
- FHIR version pinned to **R4 (4.0.1)** (design doc did not pin one).
- Validation is structural against the vendored `fhir.schema.json`,
  stdlib only — no `jsonschema` dependency, no network, no Java FHIR
  validator (mirrors `ComplianceReport/schema/` + `test_sbom_emission.py`).
- Artifacts live under the epic folder, not a new `FhirAdapter/` dir —
  `FhirAdapter/` stays unborn until the follow-on implementation epic.

**Open questions (design doc §"Open questions" — NOT closed by this epic).**
Terminology binding static/dynamic (closed: static); resource scope per
device category (still needs the full read/write matrix); `meta.security`
vs custom extension (closed: `meta.security`); legal-basis grammar (map
onto `Consent`/`Provenance`/`AuditEvent`, needs LGPD counsel); read-side
RBAC granularity (adopt SMART-on-FHIR scopes, integration with the
transport-authn epic's role model open); "break-the-glass" override (not
designed — likely alongside transport-authn).

**Watch for.** Don't let the worked example turn into grammar or codegen.
The follow-on BICEPS-style implementation epic (generated `FhirAdapter/`,
`Bundle`/`Reference` logic, `CapabilityStatement`, the identity-linkage
DSL) does not exist yet and is gated on the open questions above.
