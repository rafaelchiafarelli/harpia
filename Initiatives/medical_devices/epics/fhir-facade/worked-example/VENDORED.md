# FHIR R4 JSON Schema (vendored)

- **Standard:** HL7® FHIR® — Release 4, version **4.0.1** (the normative R4
  publication).
- **File:** `fhir.schema.json` (~3.4 MB, `$schema` draft-06, schema `id`
  `http://hl7.org/fhir/json-schema/4.0`). Covers every R4 resource; this
  epic only exercises the `Observation` definition.
- **Source:** https://hl7.org/fhir/R4/fhir.schema.json
- **License:** the FHIR specification and its published artifacts are made
  available by HL7 under the **Creative Commons "No Rights Reserved" (CC0)**
  public-domain dedication (see https://hl7.org/fhir/R4/license.html). "HL7"
  and "FHIR" are registered trademarks of Health Level Seven International.

## Why it's here

`Initiatives/medical_devices/epics/fhir-facade/` is a **design / scoping**
epic — no `FhirAdapter/` code this pass (see `../README.md`). Its one
concrete deliverable is a *hand-mapped* worked example
(`heartrate_observation.example.json`) proving Harpia's `HeartRateReading`
data model is expressible as a conformant FHIR `Observation` before any
grammar or codegen is built. This schema is the reference that example is
checked against.

`UnitTests/test_fhir_observation_example.py` validates the example's
structure against this schema's `definitions.Observation`
(`required` / property names / types) using the Python standard library
only — deliberately no `jsonschema` runtime dependency, the same posture
`ComplianceReport/schema/bom-1.5.schema.json` +
`UnitTests/test_sbom_emission.py` already take for the CycloneDX SBOM.

## To update

Replace the file from a newer R4 patch (or a later FHIR release, which is a
scoping decision — the design doc pins R4), refresh the version line above,
and adjust the structural checks in the test if `Observation`'s required
set or datatypes changed.
