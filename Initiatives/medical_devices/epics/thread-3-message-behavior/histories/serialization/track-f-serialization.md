# Track F — Serialization unification (YAML + redaction)

## Receives (must be done before this track starts)

- **F2** from Foundation (see `../thread-3-message-behavior/README.md`)
  — the `field.is_phi` flag this track's redaction keys off of.
- Nothing hard from Track E. **Flag, not a dependency:** the master plan
  describes Track F's redaction-hook design as benefiting from seeing
  Track E's `AuditSink`-on-`OnChange` pattern already built — worth
  reading `track-e-events-callbacks.md`'s Session E.3 first if available,
  but F.4 below (this track's own audited-flag session) doesn't require
  E.3 to be merged.

## Gives (what "done" means here, consumed by whom)

- `YamlAdapter/`, a unified `toString` path shared across JSON/XML/YAML,
  `phi` redaction applied uniformly by default, and an audited
  unredacted-output escape hatch.
- **Consumed by:** no other track in this thread or documented elsewhere
  in the plan set. **Flag:** the docs don't name a downstream consumer
  for this track's output — not inferring one.

## Files this track touches

- `JsonAdapter/`, `XmlAdapter/`, new `YamlAdapter/`, `Message/` `toString`
  templates (per `harpia_medical_master_plan.md` §2's track table).

---

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

## Session F.2 — Unified `toString` path across JSON/XML/YAML

- **Depends on:** F.1 merged.
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

## Session F.3 — `phi` redaction, uniform across all three formats

- **Depends on:** F.2 merged.
- **Deliverable:** fields marked `phi` are represented in `toString`
  output as a fixed redacted placeholder by default, in JSON, XML, and
  YAML alike — never omitted from the output structure, never causing an
  error or crash.
- **Tests:**
  - Unit: redaction present in all three formats for `phi` fields.

## Session F.4 — Audited unredacted-output flag

- **Depends on:** F.3 merged; F3 (Foundation) `AuditSink`.
- **Deliverable:** unredacted output only emitted when an explicit,
  non-default flag is set (e.g. `--allow-phi-print`); any use of that
  flag is itself an audited event, not a silent one.
- **Tests:**
  - Unit: unredacted flag reveals the real value AND emits an audit
    record.

## Session F.5 — Full round-trip + `ComplianceReport` note

- **Depends on:** F.1–F.4 merged.
- **Deliverable:** one-paragraph `ComplianceReport/` note describing what
  changed and why (feeds Track M later).
- **Tests:**
  - Integration: round-trip a message with `phi` fields through all
    three formats (use `HarpiaTest/test_medical.harpia` — see the thread
    README's "Watch for"); structure/keys always present, values
    redacted by default.
