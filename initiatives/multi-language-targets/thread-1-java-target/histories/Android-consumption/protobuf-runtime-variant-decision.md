### Session J.24 — Protobuf runtime variant decision

- **Depends on:** J.4 (JSON), J.10/J.11 (XML) merged — the decision needs
  to weigh what those two would lose under `javalite`.
- **Decide for real, against an actual Android build, not a guess
  (`../../README.md` §4 item 2):** full runtime (reflection-capable,
  required by J.4's `JsonFormat` and J.10/J.11's XML runtime) vs.
  `protobuf-javalite` (Android-oriented, DEX-friendly, not reflection-
  capable — loses JSON/XML for free if picked). This is the fork between
  "full symmetric target" and "what Android apps actually reach for."
- **Deliverable:** a documented decision plus the Gradle module
  configuration reflecting it, ready for J.25–J.27 to build against.
- **Tests:** none — this is a decision-and-configuration session.
