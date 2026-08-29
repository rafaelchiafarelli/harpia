## Audited unredacted-output flag

- **Depends on:** task 3 merged; F3 (Foundation) `AuditSink`.
- **Deliverable:** unredacted output only emitted when an explicit,
  non-default flag is set (e.g. `--allow-phi-print`); any use of that
  flag is itself an audited event, not a silent one.
- **Tests:**
  - Unit: unredacted flag reveals the real value AND emits an audit
    record.

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
