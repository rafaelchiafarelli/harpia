## Session D.3 — Per-field setter/accessor doc comments

- **Depends on:** F6 (shipped). No file overlap with D.2 beyond both
  living in `ProtoFile/FileCreator.py` — can run independently.
- **Expected covered by:** no medical_devices track lists
  `ProtoFile/FileCreator.py` in its Files-touched section — do this
  directly.
- **Deliverable:** a per-field doc comment, substituted per field, on
  every generated setter/accessor, emitted by `ProtoFile/FileCreator.py`'s
  field-level template, stating which of `required`/`unique`/
  `pagination[size]`/`size` modifiers apply to that field and what each
  one enforces (`../../../../doxygen-generation.md` §4 row, source:
  `README.md:296-304`).
- **Out of scope:** message-class-level doc comments (D.2).
- **Tests:**
  - Golden snapshot: one field per modifier (and one with none) — comment
    text names exactly the modifiers that apply, nothing generic.
