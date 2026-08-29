## Unified `toString` path across JSON/XML/YAML

- **Depends on:** task 1 merged.
- **Deliverable:** JSON, XML, and the new YAML adapter share one
  `toString` code path instead of three independent ones.
- **Guarantees:** `toString` never crashes, never omits structure, for
  any of the three formats.
- **Tests:**
  - Integration: round-trip a non-`phi` message through all three
    formats via the unified path.
- **Acceptance gate:** existing JSON/XML golden snapshots (14.5/14.6)
  unchanged for non-`phi` messages — this refactor must be behavior-
  preserving for the two existing formats.

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
