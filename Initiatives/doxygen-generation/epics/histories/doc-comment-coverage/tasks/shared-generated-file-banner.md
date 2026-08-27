## Session D.1 — Shared auto-generated-file banner

- **Depends on:** F6 (shipped).
- **Expected covered by:** no medical_devices track lists the shared
  file-header preamble in its Files-touched section — do this directly,
  not a Ground Rule 6 fallback.
- **Deliverable:** a short top-of-file banner comment, emitted on every
  header the generator writes via `write_if_different`
  (`Util/CLAUDE.md`), carrying the two file-wide pitfalls from
  `../../../../doxygen-generation.md` §4:
  - "Never hand-edit — regeneration silently overwrites/prunes hand
    edits" (row: *Never hand-edit generated files*).
  - "Filename is `<name>_<hash>`-qualified and gets pruned/regenerated
    when the root `.harpia` (or an import) changes" (row: *Filenames are
    `<name>_<hash>`-qualified*).
- **Out of scope:** the mainpage's full explanation of either point —
  that's already done (F6). This session is the short, per-file version.
- **Tests:**
  - Golden snapshot: a representative generated header's first N lines
    contain the banner text verbatim.
