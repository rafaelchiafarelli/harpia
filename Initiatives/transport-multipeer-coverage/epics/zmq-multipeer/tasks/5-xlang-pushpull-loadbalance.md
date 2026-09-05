## Cross-language PUSH/PULL load-balance (C++ + Java)

- **Depends on:** task 2 (same-language load-balance pattern proven first).
- **Fixture:** same message as task 2, generated for both languages from the
  same `.harpia` input.
- **Deliverable:** one sender (either language) and pullers split across
  languages: at least 2 C++ pullers + 1 Java puller (`HarpiaZmq.Receiver`
  PULL role).
  - Send 30 messages; assert the union across all pullers (both languages)
    equals exactly the 30 sent, no loss, no duplication, and neither
    language's puller received zero (same loose-distribution bound as
    task 2, now across the language boundary).
- **Out of scope:** Go/Python peers (extended later, see initiative README),
  CURVE, fairness/perf numbers.
- **Tests:** new test module, protoc+g+++pkg-config **and** gradle+JDK-gated.
