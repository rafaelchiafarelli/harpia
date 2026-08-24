### Session J.3 — `protoc --grpc_out` wiring (stub generation)

- **Depends on:** J.2 merged.
- **Deliverable:** gRPC stub generation per J.1's timing — either
  `protoc-gen-grpc-java` invoked at generation time, or the
  `protobuf-gradle-plugin` wiring extended to also run the gRPC plugin.
- **Tests:**
  - Integration: generated gRPC stub compiles and links against J.2's
    message classes.

## Implementation notes (landed 2026-08-23)

Extended `GradleAdapter` (not a new class -- see its `CLAUDE.md`) rather
than adding a second compiler class the way C++'s `ProtoCompiler`/
`GrpcCompiler` split in two: the build-time story only has one Gradle
build to configure, so both sessions own the same generated `build.gradle`.

- `project.gradle.tmpl` gained the `com.google.protobuf` plugin's `plugins
  { grpc { artifact = 'io.grpc:protoc-gen-grpc-java:1.62.2' } }` +
  `generateProtoTasks { all()*.plugins { grpc {} } }` blocks, plus
  `grpc-protobuf`/`grpc-stub`/`grpc-netty-shaded:1.62.2` dependencies and a
  `compileOnly org.apache.tomcat:annotations-api` (generated stubs
  reference `javax.annotation.Generated`, gone from the JDK classpath since
  Java 9).
- `GradleAdapter` now also copies each message's `_service.proto`, plus the
  two framework protos it imports (`errorCode.proto`/`heartBeat.proto` --
  NOT `capabilities_service.proto`, an unrelated whole-project capability
  advertisement, out of scope here). Those three static files gained
  `option java_multiple_files`/`java_package` directly in
  `Assets/proto/protofiles/` (harmless for C++, same reasoning as J.1) --
  golden snapshots updated.
- `main.py` moved the `HARPIA_GEN_LANG` block to after `copyBasicProtos`
  (was right after the `FileCreator` loop in J.2) since `errorCode.proto`/
  `heartBeat.proto` don't exist under `<dest>/proto/protofiles/` until that
  call runs.

Tests: `tests/test_java_gradle_wiring.py` extended with the service/
framework-proto structural checks and a second gradle+JDK-gated
integration test (instantiates the generated `ImplBase` to prove the stub
compiles/links, no live RPC needed) -- skipped on this host/today's Docker
image, same as J.2's.