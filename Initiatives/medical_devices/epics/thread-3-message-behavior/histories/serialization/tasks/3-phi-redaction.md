## Session F.3 — `phi` redaction, uniform across all three formats

- **Depends on:** F.2 merged.
- **Deliverable:** fields marked `phi` are represented in `toString`
  output as a fixed redacted placeholder by default, in JSON, XML, and
  YAML alike — never omitted from the output structure, never causing an
  error or crash.
- **Tests:**
  - Unit: redaction present in all three formats for `phi` fields.
