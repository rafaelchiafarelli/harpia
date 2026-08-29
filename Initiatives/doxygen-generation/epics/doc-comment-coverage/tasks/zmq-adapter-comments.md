## ZmqAdapter doc comments

- **Depends on:** F6 (shipped).
- **Expected covered by:** the zmq-lifecycle epic
  (`../../../../medical_devices/epics/zmq-lifecycle/`).
  Check whether the zmq-lifecycle epic's sessions already shipped this before picking it
  up here.
- **Deliverable:** a baseline class-level doc comment on `ZmqAdapter` — no
  specific pitfall row exists for it in
  `../../../../doxygen-generation.md` §4 yet. If this session's own read
  of `ZmqAdapter` (or the zmq-lifecycle epic's own `CLAUDE.md`, if it exists by then)
  surfaces a real consumer pitfall — e.g. socket lifecycle, reconnect
  semantics, message ordering guarantees — add a row to §4 in the same
  session and fold its content into this comment instead of leaving it
  generic.
- **Out of scope:** Database adapters (task 5).
- **Tests:**
  - Presence check (non-empty, non-generic doc comment), same shape as
    task 5's baseline items. Upgrade to a golden-snapshot content assertion
    if a §4 row gets added.
