### Session J.4 — JSON pass-through

- **Depends on:** J.2 merged.
- **Deliverable:** thin wrapper over `protobuf-java-util`'s
  `com.google.protobuf.util.JsonFormat` — same canonical protobuf-JSON
  mapping C++/Python use.
- **Tests:**
  - Unit: JSON round trip matches the canonical mapping, including a
    field name that differs under protobuf's default camelCase mapping.

## Implementation notes (landed 2026-08-23)

Deliberately does NOT mirror C++'s `JsonAdapter` shape (one generated
wrapper header per message) -- see `JavaJsonAdapter/CLAUDE.md`. protobuf-
java's `Message`/`Message.Builder` interfaces make `JsonFormat` already
generic over any message type, so a single hand-written runtime class
(`JavaJsonAdapter/runtime/HarpiaJson.java`,
`com.harpia.runtime.json.HarpiaJson`) serves every message; there is
nothing per-message left to generate. `JavaJsonAdapter.Process()` just
copies that one file in, same as `XmlAdapter` ships `harpia_xml.h`
verbatim on the C++ side.

`build.gradle` gained a `protobuf-java-util` dependency
(`GradleAdapter/templates/project.gradle.tmpl`), kept in lockstep with
`protobuf-java`.

While writing this session's integration test, J.2/J.3's own tests turned
out to be resolving their runtime classpath by hand-globbing exact jar
paths out of the Gradle dependency cache -- fragile (breaks on any pinned-
version bump or new transitive dependency, and J.4 already needed
`protobuf-java-util`'s own transitive deps). Fixed at the root instead of
patching around it a third time: `project.gradle.tmpl` now registers a
`harpiaRuntimeClasspath` task (prints the resolved runtime classpath), and
`tests/_java_gradle_helpers.py` is a new shared harness
(`generate`/`build_and_classpath`) all three Java integration test files
now use, replacing each file's own copy of that logic.

Tests: `tests/test_java_json_pass_through.py` -- structural checks (pure
Python, always run) plus a gradle+JDK-gated integration test: a
`patient_vitals` message (has a `patient_id` field, chosen specifically
for the camelCase check) round-trips through `HarpiaJson.toJson`/
`fromJson`, asserting the JSON carries `"patientId"` and never
`"patient_id"`.
