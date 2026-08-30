# Worked example — `HeartRateReading` → FHIR R4 `Observation`

Proof that Harpia's data model can express a conformant FHIR resource
**before** any grammar or `FhirAdapter/` codegen is built. Hand-mapped, one
message, one resource. The rule numbers below point at
`../README.md`'s design doc (§N) and
`../../../harpia_sensitive_data_design_rules.md` ("Rule N").

## Source message

From `harpia_sensitive_data_design_rules.md` §0 (the canonical
`HeartRateReading` form — the variants elsewhere in that doc add an
`Envelope` transport field, which is not domain data and is out of scope
for a resource mapping):

```
event message HeartRateReading {
    phi int heart_rate;
    string device_id;
} table_heart_rate;
```

## Field → element mapping

| Harpia | FHIR `Observation` element | Value in the example | Why |
|---|---|---|---|
| *(message type)* | `resourceType` | `"Observation"` | Message-level annotation (§3): `HeartRateReading` → `Observation`. A vital-sign reading is an `Observation`, not `DeviceMetric` (which models a *capability/metric descriptor*, not a single result). |
| *(message type)* | `code` | LOINC `8867-4` "Heart rate", `system http://loinc.org` | §3: the message's clinical identity is a **static compile-time literal** (§3 "terminology-code binding is decided: static"). `8867-4` is the LOINC vital-signs panel code for heart rate. |
| *(fixed)* | `status` | `"final"` | FHIR requires `status` 1..1. A completed sensor reading is `final`. The JSON schema is lenient here (only `code`/`resourceType` are `required`) but the spec is not — included so the example is spec-conformant, not just schema-parseable. |
| *(fixed)* | `category` | `vital-signs` (`observation-category` code system) | Standard US-Core / IHE categorisation for heart rate; a fixed literal, same discipline as `code`. |
| `heart_rate` (`phi int`) | `valueQuantity` | `{ value: 72, unit: "beats/minute", system: "http://unitsofmeasure.org", code: "/min" }` | §3: field-level annotation `heart_rate` → `Observation.valueQuantity`. UCUM `/min` is the units-of-measure code; `unit` is the human display. `int` → `Quantity.value` (a JSON number). |
| `heart_rate` carrying `phi` | `meta.security` | `v3-Confidentiality` `R` / restricted | §3 + **§8 spec ceiling**: `Consent`/`Provenance`/`AuditEvent` and `meta.security` all operate at **whole-resource** granularity — FHIR has no field-level confidentiality. So *any* `phi` field in the message labels the *entire* generated resource. `R` (Restricted) is the design-doc default (§3 open-question 3, closed: `meta.security`, default `R`). |
| `device_id` (`string`) | `device.identifier` | `{ system: "https://harpia.dev/fhir/identifier/<project>/device", value: "hr-monitor-00c1a4" }` | `Observation.device` is `Reference(Device | DeviceMetric)`. `device_id` is a bare external key, not a FHIR resource id. **§6 "no auto-splitting"** forbids minting a companion `Device` resource on Harpia's own initiative, so this is a **Reference by `identifier`** (find-or-match at the FHIR server, §7) with no `Reference.reference` and no `contained` Device. The `identifier.system` URI bakes in the project name (§7 minting scheme) so two projects can't collide. |
| *(fixed)* | `effectiveDateTime` | `2026-08-30T14:12:00Z` | An `Observation` needs a time the value is asserted true. `HeartRateReading` has no timestamp field in this form; the mapping supplies `effectiveDateTime` from the generation/transport time. Flagged as a gap below — a real mapping needs the message to carry it. |

## Known gaps (surfaced by this exercise, not defects to paper over)

Per Rule 5 / §2 / §5 — Harpia never fabricates a plausible value to make
output look complete. Each of these is an omission the follow-on
implementation epic must resolve **by adding a mapping input**, not by
inference:

1. **No `subject` (Patient).** `HeartRateReading` as defined carries no
   patient id, so the example emits **no `Observation.subject`**. That is
   the correct outcome here, but a clinically usable reading needs patient
   context. The sibling `AlarmEvent` message *does* have `phi string
   patient_id`; a real mapping would take `patient_id` →
   `subject.identifier` (Reference-by-identifier, same pattern as
   `device`, never a fabricated `Patient` resource). `Patient` stays
   reference-only regardless (§1, §6a).
2. **No observation timestamp field.** `effectiveDateTime` is supplied by
   the mapping layer, not the message. The follow-on grammar needs an
   explicit way for a `.harpia` author to bind a field (or the transport
   envelope's timestamp) to `effectiveDateTime` / `effectiveInstant`.
3. **`unit` display string is a mapping-supplied literal.** `"beats/minute"`
   is human text paired with UCUM `/min`; the message has no unit field.
   Fine for a fixed vital sign, but a general mapping needs the unit to be
   declared, not assumed.
4. **`device_id` semantics.** Reference-by-`identifier` assumes the
   receiving FHIR server can resolve/instantiate the `Device`. Harpia's
   generator stays stateless per compile (§7); the example does not, and
   must not, create the `Device`.

## What this proves / does not prove

- **Proves:** every field of `HeartRateReading` lands in a real, named
  R4 `Observation` element (or is a deliberate, recorded omission); the
  `phi` confidentiality obligation has a spec-native home; the result is
  structurally valid against the published R4 schema
  (`../worked-example/fhir.schema.json`, checked by
  `UnitTests/test_fhir_observation_example.py`).
- **Does not prove:** full profile/IG conformance (e.g. US Core Vital
  Signs `must-support` slicing), round-trip `from_fhir()`, `Bundle`
  semantics, or any of the design doc's open questions (LGPD legal basis,
  SMART scopes, break-the-glass). Those belong to the follow-on
  implementation epic.
