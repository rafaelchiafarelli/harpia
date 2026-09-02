# CycloneDX 1.5 JSON Schema (vendored)

- **Version:** 1.5
- **File:** `bom-1.5.schema.json`
- **Source:** https://raw.githubusercontent.com/CycloneDX/specification/1.5/schema/bom-1.5.schema.json
- **License:** Apache-2.0 (stated in the schema's own `$comment`)

The reference contract the `ComplianceReport/` SBOM (`bom.json`) is written
to satisfy. `UnitTests/test_sbom_emission.py` validates the emitted SBOM's
structure against the required fields / types / enums declared here, using
the Python standard library only — there is deliberately no `jsonschema`
runtime dependency (see `../../Initiatives/medical_devices/epics/process-artifacts/tasks/sbom-emission.md`).

To update: replace the file from a newer spec tag, bump the version above,
and adjust the structural checks in the test if required fields changed.
