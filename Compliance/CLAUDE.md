# Compliance — project-wide compliance profile (Foundation F1)

**Pipeline role:** Cross-cutting, all stages. Parsed once at generation start
(`main.py`, mirrored in `tests/run_pipeline.py`); the resulting
`ComplianceContext` is threaded into every `Stage*` constructor as an
optional `compliance=` kwarg alongside the args each already takes
(`messages`/`dest`/etc.). This is Foundation task F1 -- see
`initiatives/medical_devices/epics/thread-0-foundation/histories/ComplianceContext-plumbing-done.md`
and `initiatives/medical_devices/harpia_sensitive_data_design_rules.md` §6a.
**Plumbing only, by design:** no stage branches on these values yet (that
starts in later tracks -- Track A/C/O/...); every constructor just stores
`self.compliance` and ignores it.
**Entry points:** `load_compliance_context(path=None)` -> `ComplianceContext`.
`strictest_profile()` -> the fail-safe default. `ComplianceConfigError`
(subclass of `ValueError`) is raised, never returned, for a hard-error case.

## Files
- `context.py` — everything: three closed-set `Enum`s (`RiskClass`,
  `Topology`, `PhiHandling`), `ComplianceContext` (plus `jurisdiction`, a
  plain list of strings), `strictest_profile()`, and
  `load_compliance_context()`.

## Key facts / gotchas
- **Three failure modes, three different outcomes** -- don't conflate them:
  1. `project.harpia.yaml` missing entirely -> `strictest_profile()`, logged
     warning.
  2. File exists, one field omitted -> just that field defaults to its
     strictest value, logged warning; the rest of the file still applies.
  3. File exists, a field present with a value not in its enum (or
     `jurisdiction` not a list of strings) -> `ComplianceConfigError`
     (fatal, raised) -- never silently defaulted or ignored. `main.py`
     catches this one specifically and `exit(-1)`s, matching the
     pipeline's existing fatal-error convention even though the mechanism
     (raise, not return-an-`Error`) differs -- this happens before any
     stage runs, so there's no `Error`-returning stage to conform to yet.
- **Enum value sets were a genuine open design decision, not something any
  planning doc pinned down** (`risk_class`/`topology`/`phi_handling` are
  named throughout `harpia_medical_master_plan.md` and the design-rules doc,
  but no concrete value list existed anywhere before this task). Decided
  2026-08-23: `RiskClass` mirrors IEC 62304 (`class_a`/`class_b`/`class_c`,
  strictest=`class_c`, per design-rules doc §6); `Topology` is a
  deployment-exposure ladder (`standalone`/`networked`/`cloud_connected`,
  strictest=`cloud_connected`); `PhiHandling` is a project-level PHI policy
  (`none`/`opt_in`/`required`, strictest=`required`). Revisit if a later
  track (Track A/C/O, or Track M's paperwork templates) needs a value this
  set doesn't cover.
- **YAML library is PyYAML, not `ruamel.yaml`** despite `requirements.txt`
  listing the latter (a stale conda-buildout artifact, not actually
  installed or used by anything in the pipeline). PyYAML is already used
  elsewhere (`GuiAdapter/tool/generator.py`) and is what's actually
  available; added explicitly to `requirements.txt` and to the Docker image
  (`python3-yaml`) by this task, since the main pipeline now depends on it
  at import time (`main.py` -> `Compliance.context` -> `yaml`), not just a
  prototype tool.
- `jurisdiction` is genuinely inert for codegen -- validated as a list of
  strings and nothing more. No closed set: it feeds Track M's paperwork-
  template selection only (§6/§9 of the design-rules doc).
- Config path resolution: explicit `path=` arg, else
  `HARPIA_COMPLIANCE_CONFIG` env var, else `./project.harpia.yaml` (same
  override convention as `main.py`'s `HARPIA_INPUT_FILE`/`HARPIA_OUTPUT_DIR`).

## Touchpoints
- Called by: `main.py`, `tests/run_pipeline.py`. Every `Stage*` constructor
  across the repo accepts the resulting `ComplianceContext` as an optional
  `compliance=None` kwarg (LexicalAnalizer/, message/, protoFile/, every
  adapter under Database/, JsonAdapter/, XmlAdapter/, ZmqAdapter/,
  {Grpc,Http,Zmq}CapabilityAdapter/, TestAdapter/) but none of them act on it
  yet.
- Depends on: `logger.logger`, PyYAML (`yaml.safe_load`). No harpia-internal
  dependencies otherwise -- safe to import from anywhere without a cycle.
- Tested by: `tests/test_compliance.py`.
