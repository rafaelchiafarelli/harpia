## Session D.6 — ZmqAdapter doc comments

- **Depends on:** F6 (shipped).
- **Expected covered by:** Track B
  (`../../../../../medical_devices/epics/thread-2-transport-and-access/histories/zmq-lifecycle/track-b-zmq-lifecycle.md`).
  Check whether Track B's sessions already shipped this before picking it
  up here.
- **Deliverable:** a baseline class-level doc comment on `ZmqAdapter` — no
  specific pitfall row exists for it in
  `../../../../doxygen-generation.md` §4 yet. If this session's own read
  of `ZmqAdapter` (or Track B's own `CLAUDE.md`, if it exists by then)
  surfaces a real consumer pitfall — e.g. socket lifecycle, reconnect
  semantics, message ordering guarantees — add a row to §4 in the same
  session and fold its content into this comment instead of leaving it
  generic.
- **Out of scope:** Database adapters (D.5).
- **Tests:**
  - Presence check (non-empty, non-generic doc comment), same shape as
    D.5's baseline items. Upgrade to a golden-snapshot content assertion
    if a §4 row gets added.
