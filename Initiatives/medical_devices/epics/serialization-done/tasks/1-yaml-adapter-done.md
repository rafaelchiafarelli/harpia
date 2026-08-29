## `YamlAdapter/`

- **Depends on:** F2 (Foundation).
- **Deliverable:** new `YamlAdapter/`, mirroring the existing
  `JsonAdapter/`/`XmlAdapter/` shape for non-`phi` messages — YAML output
  parity with the other two formats, no redaction logic yet (task 3).
- **Out of scope:** unifying JSON/XML into a shared path with this new
  adapter (task 2); redaction (task 3); the audited unredacted flag (task 4).
- **Tests:**
  - Unit: YAML `toString` output for a non-`phi` message — structure and
    keys always present, matches the existing JSON/XML adapters' shape.

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
