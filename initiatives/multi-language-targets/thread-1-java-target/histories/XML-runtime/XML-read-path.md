### Session J.11 — XML read path (`from_xml`)

- **Depends on:** J.10 merged.
- **Deliverable:** the corresponding deserialization path, reusing J.10's
  reflection-walking runtime.
- **Tests:**
  - Integration: round-trip a message with nested/repeated/absent-vs-
    default-valued fields through `to_xml`→`from_xml`, confirming
    presence is preserved, not just values.
