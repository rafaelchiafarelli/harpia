

### Session J.2 — `protoc --java_out` wiring (message classes only)

- **Depends on:** J.1 merged.
- **Deliverable:** message-class generation per J.1's chosen timing —
  either harpia shells out to `protoc --java_out` at generation time, or
  emits the `build.gradle` wiring for `protobuf-gradle-plugin` to do it.
  No gRPC yet.
- **Out of scope:** gRPC stub generation (J.3).
- **Tests:**
  - Integration: generated Java message classes compile and a
    constructed instance's fields round-trip through the generated
    builder API.

## Implementation notes (landed 2026-08-23)

Per J.1's build-time decision: a new `GradleAdapter` (see its `CLAUDE.md`)
stands up a self-contained Gradle project at `<dest>/java/` —
`build.gradle` (`java` + `com.google.protobuf` plugins, `protobuf-java` +
`protoc` artifacts pinned to `3.25.3`), `settings.gradle`, and a copy of
every plain message `.proto` (reconstructed from `(msg.name, msg.md5Hash)`,
never a directory glob, so `_service.proto`/framework protos can't leak in)
under `src/main/proto/protofiles/`.

Gated behind a new `HARPIA_GEN_LANG` env var (default `cpp`, README §5's
selector mechanism — introduced here since this is the first session with
an actual Java-specific output artifact to gate; J.1's `.proto` options
didn't need it, being harmless for every target). Not a `DbBackend`-style
registry — `../../README.md` §3 explicitly defers that design choice until
a second language exists; this is the plain env-var check that seam would
eventually sit behind.

`<dest>/java/` deliberately doesn't reach outside its own tree (copies
rather than referencing `<dest>/proto/`) so it stays portable as a
standalone Gradle module — the actual motivation for J.25's Android
verification (`../../README.md` §7).

Tests: `tests/test_java_gradle_wiring.py` — structural checks (pure Python,
always run) plus a gradle+JDK-gated integration test (build + a generated-
builder round-trip), skipped on this host/today's Docker image since
neither ships a JVM toolchain yet.