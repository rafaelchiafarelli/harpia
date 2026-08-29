# Track F — Serialization unification (YAML + redaction)

Sessions live one-per-file under `tasks/`, numbered in execution order
(`1-yaml-adapter.md` … `5-full-round-trip-and-note.md`); the number is the
branch name too (Initiatives/README rules 8–11).

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

## Watch for

- Test fixture for the `phi`-spectrum sessions (F.3/F.5): the thread
  README names `HarpiaTest/test_medical.harpia` (zero-`phi` / mixed /
  fully-`phi` messages). That root file does not exist yet — the
  established pattern (Tracks A/H) is to add new `phi` fixtures to
  `HarpiaTest/Include/*.harpia` instead, so the root `test.harpia` hash
  (and every golden it pins) stays put. `patient_vitals` (mixed) and
  `alarm_event` (`phi` field) already live in `Include/file3.harpia`; a
  fully-`phi` message is the only gap.

---
