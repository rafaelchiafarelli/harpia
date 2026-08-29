## `phi` redaction, uniform across all three formats

- **Depends on:** task 2 merged.
- **Deliverable:** fields marked `phi` are represented in `toString`
  output as a fixed redacted placeholder by default, in JSON, XML, and
  YAML alike — never omitted from the output structure, never causing an
  error or crash.
- **Tests:**
  - Unit: redaction present in all three formats for `phi` fields.

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
