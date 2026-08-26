# Epic: PHI & Compliance Surface  (8-phi-and-compliance-surface)

Cross-cutting epic, **dependent on `../medical_devices/`**. The 20 schemas
already mark `phi ` fields, and codegen defaults to `risk_class=class_c`,
`topology=cloud_connected`, `phi_handling=required` (there is no
`project.harpia.yaml` in the project folders, so the strictest profile
applies). This epic documents and verifies what that actually produces in the
generated projects — it does **not** change the generator (that is
`../medical_devices/`'s job); it checks the implementation projects sit
correctly on whatever that effort ships.

Depends on: `../medical_devices/` compliance rules landing; the room epics for
the projects being audited.

| Slice | Scope | Status |
|---|---|---|
| [phi-field-inventory](histories/phi-field-inventory/) | Every `phi ` field across all 20 schemas, with the PHI-vs-not rationale — a table cross-checked against `../medical_devices/harpia_sensitive_data_design_rules.md`. | not started |
| [generated-behavior-audit](histories/generated-behavior-audit/) | What codegen currently emits for a `phi` field under `class_c` — redaction, audit hooks, encryption-at-rest via the CRUDL DAO, log scrubbing — mapped per generated artifact. | not started |
| [coordinate-with-medical-devices](histories/coordinate-with-medical-devices/) | The dependency / handoff with the sibling initiative — what it must ship for this epic to have anything to verify, and where the seam is. | not started |

Reference: `../medical_devices/harpia_medical_master_plan.md`,
`../medical_devices/harpia_sensitive_data_design_rules.md`.
Per-slice history: `histories/<slice>/`.
