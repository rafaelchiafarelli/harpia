## `ComplianceReport/` note for the serialization epic (`phi` redaction in `toString`)

- **Depends on:** the sbom-emission task merged (`ComplianceReport/` module exists).
- **Origin:** raised by the serialization epic
  (`../../serialization/`).
  The unified `toString` path renders `phi` fields, so the serialization
  epic's work is `phi`-adjacent per the effort's definition of done
  (master plan §4) and owes a traceability note — but `ComplianceReport/`
  is this epic's module, not the serialization epic's, so the note is
  written here (same as `critical-delivery-note.md` and
  `phi-db-encryption-note.md`).
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering the
  serialization epic — what changed, why, and which tests cover it — as
  raw material for the traceability-matrix task's traceability matrix:
  - **Unified `toString` (serialization tasks 1–2).** A new
    `YamlAdapter/` reflection runtime (`harpia_yaml.h` + per-message
    wrappers, same shape as JSON/XML), then one shared entry point
    `harpia::serialize::to_string(msg, Format::{JSON,XML,YAML})` /
    `from_string(text, msg*, Format)`
    (`SerializeAdapter/runtime/harpia_serialize.h`) replacing three
    separate per-format calls. For a message with **no** `phi` field it is
    a straight pass-through to the unchanged per-format engines, so
    JSON/XML output stays byte-for-byte identical (the acceptance gate).
  - **`phi` redaction, one hook, all three formats (serialization task 3).**
    When redaction is enabled (the default) and the message tree declares
    a `phi` field, `to_string` routes through a self-contained,
    format-parameterised reflection walk that emits the fixed placeholder
    `"[REDACTED]"` for every `phi` field — never omitting the field,
    never throwing. Which `(message, field)` pairs are `phi` comes from
    the generated `serialize/harpia_phi_registry.h` (from `variable.is_phi`,
    Foundation F2); the on/off state is
    `harpia::redaction::redaction_enabled()` in `harpia_redaction.h`. The
    three engines are untouched.
  - **Audited opt-out (serialization task 4).**
    `SerializeAdapter/runtime/harpia_redaction_audit.h`:
    `allow_phi_print(AuditSink& = default_audit_sink(), reason = "")`
    emits exactly one `record("phi_unredacted_output_enabled",
    "serialize.redaction", reason)` and then disables redaction;
    `restore_phi_redaction(AuditSink&)` re-enables it and records
    `"phi_unredacted_output_disabled"`. Turning redaction off is therefore
    always an audited event, never silent (design-rules Rule 5: operation
    and context names only, never the field value). This is the one place
    SerializeAdapter's runtime depends on Foundation F3's
    `compliance/harpia_audit_sink.h`.
  - **Redacted output is a lossy view, not a round-trip format
    (serialization task 5).** `from_string` is unchanged. A redacted
    document parses without error for XML/YAML (leaving `phi` fields at
    their default) and, when a `phi` field's placeholder type-matches,
    for JSON too; feeding a string placeholder back to a numeric `phi`
    field fails the JSON parse cleanly (`false`, no crash). Structure and
    keys are always preserved; `phi` values are redacted by default in
    every direction.
  - Tests: `UnitTests/test_stage10_yaml.py` (serialization task 1 output
    parity + round-trips) and `UnitTests/test_stage10_serialize.py`
    (serialization tasks 2–5): unified façade + JSON parity + non-`phi`
    byte-identity gate; `phi` redacted in all three formats with no real
    value of any scalar type surviving and every key still present;
    mixed-message redacts only its `phi` fields; the `set_redaction_enabled`
    seam; `allow_phi_print`/`restore_phi_redaction` reveal-and-audit with
    no `phi` value in the record; and a full `to_string → from_string →
    to_string` round-trip of a `phi`-bearing fixture through all three
    formats staying structurally whole and redacted by default.
    Golden-snapshotted: the per-message wrappers + `harpia_phi_registry.h`
    (`UnitTests/golden/{yaml,serialize}/`); the hand-written runtimes are
    not snapshotted (same convention as `harpia_xml.h`).
- **Tests:** covered by the traceability-matrix task's matrix spot-check (one row per annotated
  construct).

---
## Epic context — process-artifacts

**Contract.** SBOM (CycloneDX/SPDX), a traceability matrix, jurisdiction-selected
doc templates (fda/eu_mdr/anvisa), and the `ComplianceReport/` module every
`phi`-adjacent epic writes a one-paragraph note into. This is the one place
`jurisdiction[]` actually drives different output. Needs `ComplianceContext` from
Foundation. Terminal artifact — feeds the regulatory submission, not another epic
(except versioning, which extends the `ComplianceReport/` output once
sbom-emission has merged).

**Files.** New `ComplianceReport/` module.

**Watch for.** Before considering this epic done: check the `ComplianceReport/`
notes from db-encryption, transport-authn, events-callbacks / serialization, and
dds-transport actually landed — the matrix is only as complete as those notes.
