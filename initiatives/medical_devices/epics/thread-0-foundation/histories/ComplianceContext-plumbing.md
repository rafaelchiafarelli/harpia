### F1 — ComplianceContext plumbing
- **Deliverables:** `Compliance/context.py` defining
  `ComplianceContext{risk_class, topology, phi_handling, jurisdiction[]}`;
  `project.harpia.yaml` parser; `main.py` and every `Stage*` entry point
  updated to receive it.
- **Guarantees after merge:** every stage has access to the active
  compliance profile; an invalid/unknown enum value is a hard error at
  generation start, never silently ignored; missing config defaults to the
  strictest profile with a logged warning; `risk_class` is the project-
  wide hardened floor — never a per-jurisdiction fan-out (§0a);
  `jurisdiction[]` is inert for codegen, read only by Track M.
- **Out of scope:** no jurisdiction-specific *code behavior* — by design,
  per §0a, there isn't any; plumbing only.
- **Tests:**
  - Unit: valid config parses correctly; missing file → strictest default;
    invalid enum value → hard error.
  - Integration: run the full pipeline against `HarpiaTest/test.harpia`
    with a compliance config present; confirm every stage received the
    context (e.g. a per-stage smoke marker).
  - Acceptance gate: F4 baseline unaffected when no config file is present.
