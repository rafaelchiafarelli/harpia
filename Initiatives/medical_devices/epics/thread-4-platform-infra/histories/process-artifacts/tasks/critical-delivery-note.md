## Session M.x — `ComplianceReport/` note for Track D (`critical` delivery)

- **Depends on:** M.1 merged (`ComplianceReport/` module exists).
- **Origin:** raised by Track D
  (`../../../thread-6-critical-and-phi/histories/critical-delivery/track-d-critical-delivery.md`).
  `alarm_event` carries a `phi` field, so Track D's work is `phi`-adjacent
  per the effort's definition of done (master plan §4) and owes a
  traceability note — but `ComplianceReport/` is this track's module, not
  Track D's, so the note is written here.
- **Deliverable:** a one-paragraph `ComplianceReport/` note covering the
  `critical` message-type modifier, the delivery-guarantee runtime
  (`Compliance/runtime/harpia_delivery.h`), and the `ZmqAdapter` wiring —
  what changed, why, and which tests cover it — as raw material for M.2's
  traceability matrix.
- **Tests:** covered by M.2's matrix spot-check (one row per annotated
  construct).
