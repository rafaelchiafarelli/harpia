## Wire version stamps into the `ComplianceReport/` output

Scoped 2026-09-01. Task 2 of the versioning epic — and the epic's last
task. Takes task 1's `collect_git_state()` and emits its six fields as
`harpia:git_*` properties inside `bom.json`'s `metadata.properties[]`,
keeps the golden snapshot deterministic, and adds one traceability-matrix
row for build/version provenance.

### Decisions (settled during scoping — do not re-litigate)

- **Where the fields live:** `bom.json` → `metadata.properties[]`, as six
  `harpia:git_*` entries, appended **after** the existing five `harpia:*`
  pairs, in a stable order. CycloneDX 1.5 property values are strings, so
  `dirty` serializes as `"true"` / `"false"` / `"unknown"`. Not the
  CycloneDX `pedigree.commits` structure (semantically purpose-built but
  far heavier — rejected as over-engineering for "one more field").
- **Golden determinism (D3):** two layers.
  1. `collect_git_state` is reached through a module-level indirection in
     `ComplianceReport.py` (same shape as `_rfc3339_now`) so unit tests
     monkeypatch it.
  2. `UnitTests/run_pipeline.py::_collect_compliancereport` normalizes
     every `harpia:git_*` property value to a fixed sentinel before the
     golden copy — the same mechanism already used for
     `metadata.timestamp` (`"1970-01-01T00:00:00Z"`). Use a per-key
     sentinel table (e.g. `harpia:git_commit` →
     `"0000000000000000000000000000000000000000"`, `harpia:git_dirty` →
     `"false"`, everything else → `"unknown"`) so a structural reader of
     the golden still sees plausible shapes.
- **Graceful absence (D4):** when `collect_git_state` returns all
  `"unknown"` (no git / not a repo), the six properties are still present,
  each with value `"unknown"`. `bom.json` stays schema-valid. Pipeline
  exit code unchanged. This is the acceptance gate.
- **Traceability row (D6):** add **one** `Req` to
  `ComplianceReport/requirements.py` with `applies_to="project"` — build /
  version provenance as regulatory evidence. `rule_ref` points at the
  master-plan versioning contract (§5). This adds `(project)` rows to
  `traceability.{json,md}` — additive golden movement, reviewed, not a
  reshaped existing row.
- **`HARPIA_TOOL_VERSION` (D7):** bump `"0.1.0"` → `"0.2.0"` in
  `ComplianceReport.py` — the module's output shape changes. Moves
  `bom.json`'s `metadata.tools[0].version` in the golden, once.
- **No new `.harpia` fixture, no `HASH` change, no `main.py` change**
  (`ComplianceReport` is already wired in at step 15). No new module.

### Contract

**In:**
- `Util.gitstate.collect_git_state` (task 1). `ComplianceReport.Process()`
  calls it once, passing the directory of the input schema file (or the
  dest project root — implementer's call, document which); the module-level
  reference is monkeypatchable.

**Required:** task 1 merged; the process-artifacts epic's sbom-emission
task merged (shipped).

**Delivered:**
- `ComplianceReport/ComplianceReport.py`:
  - a `_git_properties()` (or extend `_harpia_properties()`) appending, in
    order: `harpia:git_commit`, `harpia:git_ref`, `harpia:git_dirty`,
    `harpia:git_describe`, `harpia:git_origin_url`,
    `harpia:git_parent_commit`. `dirty` bool → `"true"`/`"false"`;
    `"unknown"` passes through.
  - module-level `_collect_git_state = collect_git_state` indirection (or
    equivalent) for test monkeypatching.
  - `HARPIA_TOOL_VERSION = "0.2.0"`.
- `ComplianceReport/requirements.py`: one new `Req(applies_to="project")`
  for build/version provenance, `test_refs` pointing at the new tests.
- `UnitTests/run_pipeline.py::_collect_compliancereport`: normalize the
  six `harpia:git_*` property values to fixed sentinels (per-key table),
  alongside the existing `timestamp` normalization.
- `ComplianceReport/CLAUDE.md`: document the six properties, the
  `_collect_git_state` seam, the golden normalization, and that
  `git` is now an image dependency (cross-ref task 1).
- Regenerated `UnitTests/golden/compliancereport/` (`bom.json` +
  `traceability.{json,md}` + `compliance_report.md`), diff reviewed.

**Pre-work:** none beyond task 1 being merged.

**Tests:**
- Unit — `UnitTests/test_sbom_emission.py` (or a new
  `test_version_lineage.py`), pure Python, always run:
  - `collect_git_state` monkeypatched to a known six-field dict →
    `metadata.properties` carries all six `harpia:git_*` keys with exactly
    those values; `git_dirty` is the string `"true"`/`"false"`.
  - monkeypatched to all-`"unknown"` → all six present, each `"unknown"`;
    `bom.json` still passes the existing structural schema checks.
  - `metadata.tools[0].version == "0.2.0"`.
  - write-if-different: unchanged rerun doesn't move `bom.json`'s mtime.
- Integration — `skipif(shutil.which("git") is None)`, drives
  `run_pipeline.py` on `HarpiaTest`, reads the **raw** build-dir
  `bom.json` (pre-normalization): `harpia:git_commit` equals an
  independent `git rev-parse HEAD` of the harpia repo.
- Integration — the master-plan "fork" test, `skipif` on `git`:
  create a bare upstream repo, `git clone` it (so `origin/HEAD` resolves),
  drop a tiny `.harpia` + commit, generate → `harpia:git_parent_commit`
  equals the clone's fork point; add a commit on the clone, regenerate →
  `harpia:git_commit` tracks the new HEAD while `harpia:git_parent_commit`
  still points at the upstream base ("traceable back to the parent").
- Acceptance gate — generate in a tree with no `.git` (and/or `git`
  hidden from `PATH`): pipeline exits 0, `bom.json` present, all six
  `harpia:git_*` properties present with `"unknown"`.
- Golden — `test_golden.py::test_compliancereport` passes after
  regeneration; the diff is only the six normalized `harpia:git_*` props +
  the additive `(project)` traceability rows + the `0.2.0` tool version.

**Out of scope:** anything beyond git lineage in `bom.json` — no
`SdcAdapter`-style new module, no `.harpia` grammar, no CycloneDX
`pedigree`, no per-message version stamping. The epic is done when this
merges.

---
## Epic context — versioning

See `1-git-fork-tracking-metadata-collection.md` → "Epic context" for the
full epic contract, receives/gives, and the files map. This task closes
the epic: `tasks` → `versioning` → `epics` once it and task 1 are both in.
