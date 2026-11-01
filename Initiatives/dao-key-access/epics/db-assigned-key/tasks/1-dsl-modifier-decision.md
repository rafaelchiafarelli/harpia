## Decide the `.harpia` opt-in for a database-assigned key

- **Depends on:** nothing. **Deliverable: a decision, recorded in this file
  and in `../../README.md`, plus the lexer/grammar contract for tasks 2–4.**
  No generator code.
- Standing principle: the generator never infers this; the schema says it.
- **Options:**
  1. **Message-level modifier** before `message`, beside `protected`/`open`
     (e.g. `autokey message P { ... } p_table;`). Recommended: per table,
     explicit, same lexer path as the hardening modifiers.
  2. **Project-wide** `project.harpia.yaml` setting — one switch, but hides a
     per-table storage choice outside the schema.
- **Questions to settle with it:** `create` with `HARPIA_ID` already set —
  error or honoured? (recommended: error, one source of truth); the assigned
  key written back into the caller's message (recommended: yes); PG uses
  `GENERATED ... AS IDENTITY`; migration of an existing caller-assigned table
  to auto (recommended: allowed, the column type doesn't change on SQLite;
  PG adds the identity).
- **Docs:** the modifier in `USAGE.md` §3 once decided.
