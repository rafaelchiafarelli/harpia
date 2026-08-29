## Session M.3 — Jurisdiction-selected doc templates

- **Depends on:** M.1, M.2 merged.
- **Deliverable:** jurisdiction-selected doc templates (fda/eu_mdr/anvisa)
  — same underlying SBOM + traceability evidence, different paperwork
  shell per `jurisdiction[]`.
- **Tests:**
  - Integration: output format correctly follows the selected
    jurisdiction's template.
- **Acceptance gate:** doc output differs correctly across the three
  jurisdiction templates for the *same* underlying evidence (same SBOM,
  same traceability rows — only the template shell changes).