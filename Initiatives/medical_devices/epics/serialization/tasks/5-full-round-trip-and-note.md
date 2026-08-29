## Full round-trip + `ComplianceReport` note

- **Depends on:** task 1–task 4 merged.
- **Deliverable:** one-paragraph `ComplianceReport/` note describing what
  changed and why (feeds the process-artifacts epic later).
- **Tests:**
  - Integration: round-trip a message with `phi` fields through all
    three formats (use the `HarpiaTest/Include/*.harpia` phi fixtures — see epics/README.md
    README's "Watch for"); structure/keys always present, values
    redacted by default.

---
## Epic context — serialization

**Contract.** New `YamlAdapter/`; one `toString` path shared across JSON/XML/YAML;
`phi` values redacted by default in all three; an audited opt-out for unredacted
output. Needs only the `phi` field tag from Foundation. No downstream consumer is
named in the plan.

**Files.** `JsonAdapter/`, `XmlAdapter/`, new `YamlAdapter/`, `Message/` `toString`
templates.

**Watch for.** `phi`-spectrum fixtures live in `HarpiaTest/Include/*.harpia`
(`patient_vitals` mixed, `alarm_event` has a `phi` field; a fully-`phi` message
was added here) — never a new root `test.harpia`, which would move every pinned
golden `HASH`.
