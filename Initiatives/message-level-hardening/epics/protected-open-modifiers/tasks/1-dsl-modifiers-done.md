## `protected` / `open` message-level modifiers (DSL front end)

- **Depends on:** nothing (existing `critical`/`dds` modifier pattern).
- **Deliverable:**
  - Two new tokens in `LexicalAnalizer/LexicalAnalyzer.py`, same slot/shape as
    `CRITICAL`/`DDS` (`r'protected '` / `r'open '`, trailing-space lexed,
    sits before `message `, composes freely with transport-kind modifiers and
    with each other's absence).
  - `Message.py`: `is_protected` / `is_open` booleans (default `False`,
    mirroring `is_critical`/`is_dds`), set from `access_modifiers` the same
    way. If both are present on one message, return an `Error` (new
    `Types` entry, e.g. `CONFLICTING_HARDENING_MODIFIERS`) at generation
    time — do not pick a winner.
  - No adapter reads either flag yet in this task — flag-only, exactly like
    `is_dds`/`is_critical` were on landing. A message using neither modifier
    must emit byte-identical `.proto`/DB/JSON/XML/YAML output to before this
    task (verify via `UnitTests/test_golden.py`/`test_golden_java.py` with
    `HARPIA_UPDATE_GOLDEN` **unset** — no golden diff expected at all).
- **Out of scope:** anything reading these flags (tasks 3+), the mTLS spike
  (task 2, independent).
- **Tests:** a small new fixture message pair (`Include/`, not `test.harpia`
  per the repo-wide rule) — one `protected message`, one `open message`,
  neither table-bearing needed yet — asserting `Message.is_protected` /
  `is_open` parse correctly, and a third fixture message with both modifiers
  asserting the generation error fires.
