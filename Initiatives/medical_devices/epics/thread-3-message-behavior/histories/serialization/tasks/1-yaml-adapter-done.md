## Session F.1 — `YamlAdapter/`

- **Depends on:** F2 (Foundation).
- **Deliverable:** new `YamlAdapter/`, mirroring the existing
  `JsonAdapter/`/`XmlAdapter/` shape for non-`phi` messages — YAML output
  parity with the other two formats, no redaction logic yet (F.3).
- **Out of scope:** unifying JSON/XML into a shared path with this new
  adapter (F.2); redaction (F.3); the audited unredacted flag (F.4).
- **Tests:**
  - Unit: YAML `toString` output for a non-`phi` message — structure and
    keys always present, matches the existing JSON/XML adapters' shape.
