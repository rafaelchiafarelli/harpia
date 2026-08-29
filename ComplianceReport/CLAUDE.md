# ComplianceReport — per-project compliance artifacts (process-artifacts epic)

**Pipeline role:** last stage (step 15, after `TestAdapter`). The
`medical_devices` **process-artifacts** epic's module (epic complete). Emits,
per generation, for the *generated project*: a CycloneDX 1.5 SBOM
(`sbom-emission`), a requirement→code→evidence traceability matrix
(`traceability-matrix`), and one or more jurisdiction-selected compliance
report shells (`jurisdiction-template-selection`). The `versioning` epic
extends this module later with version/git lineage.

**Entry point (from `main.py` / `run_pipeline.py`):**
`ComplianceReport(messages, dest, compliance=complianceContext).Process()`.
Returns `None` (always — the artifacts are always meaningful; no
`NOTHING_TO_REPORT`).

**Inputs → Outputs:**
- `compliance` (`ComplianceContext`, F1) → the five SBOM `metadata.properties`
  (`harpia:risk_class` / `topology` / `phi_handling` / `crypto_backend` /
  `jurisdiction`).
- `<dest>/build_metadata/crypto_backend.json` (F5, already written by the
  pipeline) → the `harpia:crypto_backend` value; `"unknown"` if absent.
- `messages` — walked by the traceability matrix (one row per `phi` field /
  `critical` message × applicable requirement). Unused by the SBOM.
- `components.VENDORED` / `components.ENVIRONMENT` → the SBOM component list.
- `requirements.REQUIREMENTS` → the traceability matrix's requirement catalog.
- `jurisdictions.JURISDICTIONS` (FDA / EU_MDR / ANVISA) + `GENERIC` → the
  per-jurisdiction header-block values; `templates/compliance_report.md.tmpl`
  → the shared report layout (`{{placeholder}}` markers, filled by
  `str.replace`).
- Emits (all write-if-different) into `<dest>/generated/ComplianceReport/`:
  `bom.json`, `traceability.json` (source of truth), `traceability.md`
  (rendered review table), `compliance_report.md` (always — generic shell),
  and `compliance_report.<token>.md` for each entry in
  `compliance.jurisdiction` (unknown token → generic shell + a note, never
  an error).

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
- `requirements.py` — the **checked-in** compliance requirements catalog
  (`Req(id, rule_ref, applies_to, text, mechanism, test_refs)`), seeded from
  `harpia_sensitive_data_design_rules.md` Rules 0/1/3/4a/5/6a and the
  folded-in `*-note.md` files (serialization / db-encryption /
  critical-delivery). `applies_to` ∈ `phi_field` / `phi_field_table` (phi
  field on a table-bearing message only) / `critical_message` / `project`.
  A future note-producing task **adds an entry here**, not a prose file.
- `ComplianceReport.py` `_traceability_rows()` — walks `self.messages`,
  cross-joins each `phi` field / `critical` message with the catalog
  entries that apply, plus the fixed `project` rows; sorted by
  `(construct, requirement_id)`; no timestamp. `_traceability_table()` is
  the bare Markdown table shared by `traceability.md` and the reports;
  `_sbom_table()` renders `bom.json`'s components.
- `ComplianceReport.py` `_jurisdiction_reports()` / `_render_report()` —
  same evidence (`_sbom_table` + `_traceability_table`), jurisdiction-
  specific header only. Token match is case/separator-insensitive
  (`jurisdictions.resolve`).

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
- Tested by: `UnitTests/test_sbom_emission.py` (SBOM structure vs the
  vendored schema, `harpia:*` properties, vendored-version resolution,
  `unknown` degradation, write-if-different); `UnitTests/test_traceability.py`
  (row well-formedness, catalog-derived row count, table-less phi field gets
  redaction but no DB rows, critical-message rows, evidence spot-checks,
  determinism, no-timestamp); `UnitTests/test_jurisdiction_templates.py`
  (generic + one report per jurisdiction, identical evidence section across
  jurisdictions, distinct header blocks, EU MDR tamper-evidence note,
  empty/unknown-token handling, case-insensitive match, disclaimer present);
  `UnitTests/test_golden.py::test_compliancereport` (normalized `bom.json` +
  `traceability.{json,md}` + generic `compliance_report.md` snapshot).
  `test_compliance.py`'s `compliance_smoke.txt` check covers the pipeline
  wiring.
- Extended later by: the `versioning` epic (version/git lineage fields).
