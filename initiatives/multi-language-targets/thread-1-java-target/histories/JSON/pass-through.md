### Session J.4 — JSON pass-through

- **Depends on:** J.2 merged.
- **Deliverable:** thin wrapper over `protobuf-java-util`'s
  `com.google.protobuf.util.JsonFormat` — same canonical protobuf-JSON
  mapping C++/Python use.
- **Tests:**
  - Unit: JSON round trip matches the canonical mapping, including a
    field name that differs under protobuf's default camelCase mapping.
