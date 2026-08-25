## Session D.2 — Message class doc comments

- **Depends on:** F6 (shipped).
- **Expected covered by:** no medical_devices track lists
  `protoFile/FileCreator.py` in its Files-touched section — do this
  directly.
- **Deliverable:** a class-level doc comment on every generated message
  class, emitted by `protoFile/FileCreator.py`'s message-class template,
  carrying two rows from `../../../../doxygen-generation.md` §4:
  - Hidden trailer fields (`ID_`, `STATUS_`, `ERROR_`, `ORIGINATOR`) exist
    on every message even though the user didn't declare them (source:
    `util/CLAUDE.md` `_HIDDEN_PREFIXES`, `message/Variables.py
    AddHiddenVariables`).
  - `table_name` trailing `;` means private (owner-only) vs public
    visibility — substituted per message, not generic (source:
    `README.md:315-320`).
- **Out of scope:** per-field doc comments (D.3).
- **Tests:**
  - Golden snapshot: one message with a private (`;`-suffixed)
    `table_name` and one without, asserting the visibility note differs
    correctly between the two.
  - Golden snapshot: the hidden-trailer-fields note is present verbatim
    on any generated message class.
