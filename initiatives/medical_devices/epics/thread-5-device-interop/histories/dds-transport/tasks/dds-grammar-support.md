## Session P.1 — `dds` grammar support

- **Depends on:** F1 (Foundation).
- **Deliverable:** new `dds` transport-modifier value in
  `LexicalAnalizer/`/`Message/`, composable the same way `push`/`pull`/
  `event`/`stream` are today — a message picks `dds` when it needs to be
  published onto/read from a DDS bus, independent of whether it's also
  reachable via ZMQ or gRPC.
- **Tests:**
  - Unit: `dds` composes correctly with `phi`, `optional`, `repeteable`
    per existing modifier-composition tests.
