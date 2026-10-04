## Unified `to_string` façade + `phi` redaction + audited opt-out

- **Depends on:** tasks 1–3; `py-foundation` task 4 (`AuditSink`).
- **Contract:** a port of `SerializeAdapter/` (read its `CLAUDE.md`
  first).
  - `harpia_runtime/serialize.py`:
    - `Format` (`JSON`/`XML`/`YAML`), `to_string(msg, fmt)`,
      `from_string(text, msg, fmt)`, `format_name(fmt)`.
    - A message tree with no `phi` field goes **straight through** to the
      task 1–3 engines (byte-identical to calling them directly).
    - A phi-bearing tree (recursive, cycle-guarded) renders through one
      redacting walk that prints `[REDACTED]`: quoted for JSON/YAML, bare
      for XML.
  - `harpia_runtime/redaction.py`: `PLACEHOLDER`, `redaction_enabled()`
    (default `True`), `set_redaction_enabled(bool)`,
    `should_redact(message, field)`.
  - `harpia_runtime/redaction_audit.py`: `allow_phi_print(sink=default,
    reason="")` records `phi_unredacted_output_enabled` and then disables
    redaction. `restore_phi_redaction(sink)` re-enables and then records
    `phi_unredacted_output_disabled`. This is the only module here that
    imports the compliance runtime.
  - **generated** `harpia_generated/serialize/phi_registry.py`: the
    schema's `(message, field)` phi pairs + `is_phi()` /
    `message_has_phi()`, from `variable.is_phi`.
- **Bar:**
  - Non-phi messages are byte-identical to the engines.
  - Redacted output for phi messages is byte-identical to the C++
    `redacted_to_string` walk. This is a deliberate port of its
    formatting, including its quirk of printing proto3 default scalars.
  - Redacted text is a lossy view: `from_string` of redacted JSON fails;
    of redacted XML/YAML it leaves phi fields at their default.
- **Out of scope:** encryption at rest (`py-crypto-phi`).
- **Tests:**
  - Golden snapshot of `phi_registry.py`.
  - Unit tests: redaction in all three formats, mixed messages, non-phi
    bypass, the toggle, and `allow_phi_print`/`restore_phi_redaction`
    recording exactly one entry each with no value in any argument.
  - A protoc+g++-gated byte-parity test of redacted output against C++
    (`test_stage10_serialize.py` shape).
