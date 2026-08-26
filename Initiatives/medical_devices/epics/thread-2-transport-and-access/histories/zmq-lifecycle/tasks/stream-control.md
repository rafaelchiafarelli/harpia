## Session B.1 — `stream[#]` setup/read/stop + timeout

- **Depends on:** F1 (Foundation). Builds on the already-shipped CURVE
  transport — verify it meets this session's guarantees before extending.
- **Deliverable:** full `stream[#]` lifecycle (setup/read/stop) per the
  process.md spec, with timeout handling.
- **Guarantees:** `read` returns IN-VALID on timeout/stop per spec.
- **Tests:**
  - Unit: invalid stream config → IN-VALID.
  - Integration: extend `test_demo_message_crosses_with_curve`
    (`UnitTests/test_demo.py`) with a timeout scenario — don't duplicate the
    existing CURVE round-trip coverage.