# ComplianceReport — per-project compliance artifacts (process-artifacts epic)

**Pipeline role:** last stage (step 15, after `TestAdapter`). Created by the
`medical_devices` **process-artifacts** epic / `sbom-emission` task. Currently
emits one artifact — a CycloneDX 1.5 SBOM for the *generated project* — and is
the module the epic's later tasks (traceability matrix, jurisdiction doc
templates) and the `versioning` epic extend.

**Entry point (from `main.py` / `run_pipeline.py`):**
`ComplianceReport(messages, dest, compliance=complianceContext).Process()`.
Returns `None` (always — the SBOM is always meaningful; no `NOTHING_TO_REPORT`).

**Inputs → Outputs:**
- `compliance` (`ComplianceContext`, F1) → the five `metadata.properties`
  (`harpia:risk_class` / `topology` / `phi_handling` / `crypto_backend` /
  `jurisdiction`).
- `<dest>/build_metadata/crypto_backend.json` (F5, already written by the
  pipeline) → the `harpia:crypto_backend` value; `"unknown"` if absent.
- `messages` — accepted for constructor-signature parity with the other
  stages, **unused** here (the traceability-matrix task will use it).
- `components.VENDORED` / `components.ENVIRONMENT` → the component list.
- Emits `<dest>/generated/ComplianceReport/bom.json` (write-if-different).

## Files
- `ComplianceReport.py` — `Process()` builds the CycloneDX dict and writes
  `bom.json`. `_build_bom` / `_harpia_properties` / `_components` /
  `_crypto_backend`. `_rfc3339_now()` is the only non-deterministic bit
  (monkeypatch it in tests; the golden collector normalizes it).
- `components.py` — the **declared** runtime-dependency manifest (not scraped
  from CMake — the standing "declare, don't infer" rule). `VENDORED` resolve
  version/license/source from `third_party/<dir>/VENDORED.md` (`_field` reads
  a `- **Label:** value` line, truncating at the first `(` or `;`).
  `ENVIRONMENT` (protobuf/grpc/libzmq — from the toolchain, not vendored)
  resolve via `protoc --version` / `pkg-config --modversion`. Every resolver
  falls back to `components.UNKNOWN` (`"unknown"`); nothing is ever dropped
  or raised.
- `schema/bom-1.5.schema.json` — vendored CycloneDX 1.5 JSON Schema
  (`schema/VENDORED.md`). The reference contract; **not** a runtime
  dependency — `test_sbom_emission.py` validates structure against it with
  the stdlib only (no `jsonschema` install, no Docker image change).

## Key facts / gotchas
- **`jurisdiction[]` is inert here** (master plan §0a). It is recorded as one
  `metadata.property` and nothing else; SBOM *content* never branches on it.
  Only the `jurisdiction-template-selection` task (task 3) consumes it, and
  only to pick a paperwork shell over identical evidence.
- **`components[]` is sorted by `name`** for a stable diff; vendored entries
  with a real (non-`unknown`) version also get a `purl`, `licenses[]` and a
  `vcs` `externalReferences[]` entry.
- **Environment versions come from the Docker toolchain** and are snapshotted
  in `UnitTests/golden/compliancereport/bom.json` as-is — a protobuf/grpc/zmq
  bump in the image will move the golden, same as it already would elsewhere
  in the suite (`HARPIA_UPDATE_GOLDEN=1`, review the diff).
- The generated-project component (`metadata.component`, `type: application`)
  is named from `compliance.project` (default `"default"`).

## Touchpoints
- Called by: `main.py` (step 15), `UnitTests/run_pipeline.py` (step 15 +
  `_collect_compliancereport`, which normalizes `metadata.timestamp`).
- Depends on: `Logger.logger`, `Util.util.write_if_different`,
  `ComplianceReport.components`; reads `third_party/*/VENDORED.md` and
  `<dest>/build_metadata/crypto_backend.json`.
- Tested by: `UnitTests/test_sbom_emission.py` (structure vs the vendored
  schema, `harpia:*` properties, vendored-version resolution, `unknown`
  degradation, write-if-different) and
  `UnitTests/test_golden.py::test_compliancereport` (normalized `bom.json`
  snapshot). `test_compliance.py`'s `compliance_smoke.txt` check covers the
  pipeline wiring.
- Extended later by: the process-artifacts `traceability-matrix` and
  `jurisdiction-template-selection` tasks, and the `versioning` epic.
