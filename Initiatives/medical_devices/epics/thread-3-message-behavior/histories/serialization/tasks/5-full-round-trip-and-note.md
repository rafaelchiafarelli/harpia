## Session F.5 — Full round-trip + `ComplianceReport` note

- **Depends on:** F.1–F.4 merged.
- **Deliverable:** one-paragraph `ComplianceReport/` note describing what
  changed and why (feeds Track M later).
- **Tests:**
  - Integration: round-trip a message with `phi` fields through all
    three formats (use `HarpiaTest/test_medical.harpia` — see the thread
    README's "Watch for"); structure/keys always present, values
    redacted by default.
