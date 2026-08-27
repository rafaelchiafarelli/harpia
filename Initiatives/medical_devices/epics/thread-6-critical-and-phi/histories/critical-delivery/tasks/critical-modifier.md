## Session D.1 — `critical` message-type modifier

**Status:** done — `b433dd5`.

- **Depends on:** none.
- **Deliverable:** lexer token `('CRITICAL', r'critical ')` (keyword-only,
  trailing space, same slot as `EVENT`/`STREAM`); `Message.is_critical` set
  when `CRITICAL` is in `access_modifiers`. Composes with any transport
  kind, order-independent. Flag only — emitted `.proto` byte-identical to
  the same message without `critical`.
- **Fixture:** `critical event message alarm_event` added to
  `HarpiaTest/Include/file3.harpia` (carries a `phi` field too — Rule 0,
  the axes are independent).
- **Out of scope:** any delivery machinery (that is D.2/D.3).
- **Tests:** `UnitTests/test_critical_modifier.py` (12); `run_phi_check.py`
  extended to report per-message `is_critical`.
