## SBOM emission — `ComplianceReport/` module + CycloneDX SBOM

Scoped 2026-08-29. This is task 1 of the process-artifacts epic: it stands up
the `ComplianceReport/` module every other task in this epic (and the
versioning epic) hangs off, and makes it emit a schema-valid SBOM.

### Decisions (settled during scoping — do not re-litigate)

- **Format:** CycloneDX 1.5, JSON. Not SPDX, not both.
- **Scope:** the *generated project's* runtime dependencies — what a device
  built with Harpia actually ships — not the generator's own toolchain.
- **Module shape:** a per-generation Python module like the adapters
  (`SerializeAdapter/`, `Doxygen/`), wired into `main.py` +
  `UnitTests/run_pipeline.py`, emitting into `<dest>/generated/`.
- **Validation:** stdlib-only structural checks in the test against a
  **vendored reference** `ComplianceReport/schema/bom-1.5.schema.json`
  (official CycloneDX 1.5 JSON Schema, checked in). No `jsonschema` /
  `cyclonedx` dependency, no Docker image change.
- **Not split** — module scaffold + SBOM emission + validation is one
  contract.

### Contract

**In:**
- `compliance` (`ComplianceContext`, F1) — `risk_class`, `topology`,
  `phi_handling`, `jurisdiction[]`, `project`.
- `dest` — output root.
- `messages` — accepted for constructor-signature parity with the other
  stages; **not used** by SBOM emission itself (the traceability-matrix
  task will use it).
- `<dest>/build_metadata/crypto_backend.json` — already written by
  `run_pipeline.py` / `main.py` via `write_build_metadata` (F5); the
  selected crypto backend becomes an SBOM property.
- A **declared component manifest** `ComplianceReport/components.py`: the
  known Harpia-runtime dependency set — for each: `name`, short
  `description`, CycloneDX `type` (`library`), PURL type where meaningful,
  and a version resolver. Declared, not scraped from CMake (an explicit
  declaration, per the standing "don't infer what should be declared"
  rule). Initial set: `asio`, `crow`, `sqlite`, `tinyxml2` (vendored —
  parse the version out of the vendored header/tree), `protobuf`, `grpc`,
  `libzmq` (from the build environment — `protoc --version` /
  `pkg-config --modversion` / `dpkg-query`, in that order of preference).
  Every resolver falls back to the string `"unknown"` — never omits the
  component, never raises.

**Required:** F1 merged (shipped). `build_metadata/crypto_backend.json`
emitted (already the case). No dependency on any other process-artifacts
task — this is task 1.

**Delivered (the contract downstream tasks build on):**
- `ComplianceReport.ComplianceReport` class, constructor
  `(messages, dest, compliance=None)`, `Process(self)` returning `None`
  or `Error` (`NOTHING_TO_REPORT` shape — mirror `SerializeAdapter`).
- `<dest>/generated/ComplianceReport/bom.json`, valid CycloneDX 1.5:
  - `bomFormat: "CycloneDX"`, `specVersion: "1.5"`, `version: 1`,
    `$schema` set.
  - `metadata.timestamp` (RFC3339 UTC), `metadata.tools[]` = one entry
    for harpia, `metadata.component` = the generated project
    (`type: "application"`, `name` from `compliance.project`,
    `bom-ref`).
  - `metadata.properties[]`: `harpia:risk_class`, `harpia:topology`,
    `harpia:phi_handling`, `harpia:crypto_backend`,
    `harpia:jurisdiction` (comma-joined — **inert metadata only**, master
    plan §0a; the SBOM content never branches on it).
  - `components[]`: one `library` entry per manifest component —
    `type`, `name`, `version`, `bom-ref`, `description`, and `purl`
    where the resolver produced a real version.
- `ComplianceReport/schema/bom-1.5.schema.json` — vendored reference.
- Deterministic except for `metadata.timestamp`; the golden collector
  normalizes that field to a fixed value so `test_golden.py` can snapshot
  `bom.json` (or excludes it — collector's choice, documented in
  `run_pipeline.py`).
- `main.py`: `ComplianceReport(...).Process()` after `TestAdapter` (last
  stage). `run_pipeline.py`: `_mark("ComplianceReport", ...)` in the same
  position + a `_collect_compliancereport` into a snapshot subdir.
- `ComplianceReport/CLAUDE.md` (module reference note, house style).

**Pre-work (all inside this task; none needs separate scoping):**
- Fetch + vendor `bom-1.5.schema.json` from
  `github.com/CycloneDX/specification` (single asset file). If the
  implementing session has no network, author the structural checks from
  the published 1.5 spec and add the file in the same task once
  reachable — non-blocking.
- No new `.harpia` fixtures (SBOM is schema-independent; runs on the
  existing `HarpiaTest` pipeline).
- No Docker image change.

**Tests:**
- Unit (pure Python, always run): `Process()` writes `bom.json`; it
  parses as JSON; structural assertions against the vendored schema's
  required fields/types/enums — `bomFormat`/`specVersion` exact,
  `metadata.component` present, every `components[]` entry has
  `type in {library,application,framework,…}` + non-empty `name` +
  `version`; `metadata.properties` carries the five `harpia:*` keys with
  the loaded `ComplianceContext`'s values; write-if-different (stable
  mtime on an unchanged rerun).
- Integration: a full `run_pipeline.py` on `HarpiaTest` produces a
  `bom.json` listing at least `asio`, `crow`, `sqlite`, `tinyxml2`,
  `protobuf`, each with a non-empty `version` or the explicit
  `"unknown"` sentinel (never missing).
- Golden: `test_golden.py` snapshots the normalized `bom.json`.

**Out of scope (later tasks):** traceability-matrix rows (task 2);
folding `critical-delivery-note.md` / `phi-db-encryption-note.md` /
`serialization-redaction-note.md` into the report (task 2);
jurisdiction-selected doc-template shells (task 3); version / git lineage
fields (versioning epic, which extends this module once this task merges).

---
## Epic context — process-artifacts

**Contract.** SBOM (CycloneDX/SPDX), a traceability matrix, jurisdiction-selected
doc templates (fda/eu_mdr/anvisa), and the `ComplianceReport/` module every
`phi`-adjacent epic writes a one-paragraph note into. This is the one place
`jurisdiction[]` actually drives different output. Needs `ComplianceContext` from
Foundation. Terminal artifact — feeds the regulatory submission, not another epic
(except versioning, which extends the `ComplianceReport/` output once
sbom-emission has merged).

**Files.** New `ComplianceReport/` module.

**Watch for.** Before considering this epic done: check the `ComplianceReport/`
notes from db-encryption, transport-authn, events-callbacks / serialization, and
dds-transport actually landed — the matrix is only as complete as those notes.
