### Session J.11 — XML read path (`from_xml`)

- **Depends on:** J.10 merged.
- **Deliverable:** the corresponding deserialization path, reusing J.10's
  reflection-walking runtime.
- **Tests:**
  - Integration: round-trip a message with nested/repeated/absent-vs-
    default-valued fields through `to_xml`→`from_xml`, confirming
    presence is preserved, not just values.

## Implementation notes (landed 2026-08-23, together with J.10)

Extends the same `HarpiaXml.java` J.10 introduces: `fromXml(String,
Message.Builder)` (returns `false` on a parse failure, boolean-outcome
convention matching `is_valid_json`/the repo's other `from_*` functions)
+ `readMessage()` (walks `Element` children via `Descriptor.
findFieldByName(tag)` — the child element's tag name IS the exact
`.proto` field name, same reflection-by-exact-name strategy `JdbcBind`
already uses for the DB layer, `JavaDatabase/CLAUDE.md`) + `parseScalar()`
(text -> boxed value per `FieldDescriptor.JavaType`, enum resolved by name
first then falling back to number). A nested message field recurses via
`builder.newBuilderForField(fd)`.

Test (`tests/test_java_xml.py::test_nested_repeated_and_presence_roundtrip`):
round-trips `shipment` (nested + repeated) and `patient_vitals` in both
its `device_note`-set and -unset forms — the unset case is the one that
actually proves presence survived: `hasDeviceNote()` must come back
`false`, not just an empty string, after the round trip.
