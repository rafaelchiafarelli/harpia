### F2 — `phi` field modifier

**Status: done (2026-08-23), on `feature/thread-0-foundation`, not yet merged
to `main`.** Implemented as a `PHI r'phi '` lexer token
(`LexicalAnalizer/LexicalAnalyzer.py`) plus a `variable.is_phi` flag set in
`message/Variables.py`'s field loop -- parsed identically to `optional`/
`required`/`unique` (keyword-only, composes with any other modifier in any
order, including on composed-type fields). No other file touched: `is_phi`
reaches every later stage automatically since it lives on the same
`variable` objects already threaded everywhere. Confirmed flag-only: emitted
`.proto` for a `phi` field is line-for-line identical to the same field
without it. All three test layers below pass (`tests/test_phi_modifier.py`
+ `tests/run_phi_check.py`; golden/F4 baseline and `test_frontend.py`
confirmed unaffected; full Docker toolchain suite shows no new failures).

- **Deliverables:** grammar + AST support for `phi` in
  `LexicalAnalizer/`/`Message/`; `field.is_phi` flag available to every
  later stage.
- **Guarantees:** fields without `phi` behave exactly as before, byte-for-
  byte; `phi` composes correctly with existing modifiers.
- **Out of scope:** no encryption, redaction, or audit logic — flag only.
- **Tests:**
  - Unit: parse messages with/without `phi`, alone and combined with other
    modifiers; confirm AST flags.
  - Integration: Stages 0–6 on a `.harpia` file with `phi` fields produce a
    clean `.proto`.
  - Acceptance gate: existing snapshot tests for non-`phi` messages
    unchanged.
