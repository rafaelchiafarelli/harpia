# GradleAdapter — Java target: message-class + gRPC stub generation (build-time Gradle wiring)

**Pipeline role:** Java-target Stage 6/7/13 equivalent (sessions J.2/J.3, `Initiatives/multi-language-targets/thread-1-java-target`). Stands up a self-contained Gradle project under `<dest>/java/`, wired with `protobuf-gradle-plugin` (+ its `grpc` plugin), so the *consumer's* `gradle build` generates both the Java message classes and the gRPC stub classes — harpia itself never shells out to `protoc`/`protoc-gen-grpc-java` for Java. Resolved build-time (see "Why build-time codegen" below), unlike every other stage in this repo, which commits generated source at harpia generation time.
**Entry point (from main.py):** gated behind `HARPIA_GEN_LANG` (default `cpp`, unaffected): `if os.environ.get("HARPIA_GEN_LANG", "cpp") == "java": GradleAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()`, called after `copyBasicProtos` (needs `<dest>/proto/protofiles/{errorCode,heartBeat}.proto` to already exist, not just the per-message ones `FileCreator`'s loop wrote). Returns `None` or an `Error` (non-fatal; main.py logs it).
**Inputs → Outputs:** consumes message objects (`msg.name`, `msg.md5Hash` — same filename convention as `FileCreator`). Reads `<dest>/proto/protofiles/{<name>_<hash>.proto, <name>_<hash>_service.proto, errorCode.proto, heartBeat.proto}` — all already carrying `option java_multiple_files`/`java_package` (message protos since J.1; the other three since J.3, added directly to their static Asset source files). Emits `<dest>/java/build.gradle`, `<dest>/java/settings.gradle`, and a **copy** of each of the above under `<dest>/java/src/main/proto/protofiles/`.

## Files
- `GradleAdapter.py` — `Process()` makes `src/main/proto/protofiles/`, writes the two static Gradle files (`write_if_different`), then copies (`copy_if_different`) every message's `.proto` **and** `_service.proto`, plus the two framework protos (`_FRAMEWORK_PROTOS = ("errorCode.proto", "heartBeat.proto")`), from `<dest>/proto/protofiles/`. Per-message filenames are reconstructed from `(msg.name, msg.md5Hash)` — NOT a directory glob — so `capabilities_service.proto` (an unrelated whole-project gRPC capability advertisement, see `GrpcCapabilityAdapter/CLAUDE.md`) can never accidentally leak in. Returns `NOTHING_TO_REPORT` (`Errors.Classes.MESSAGES`) if nothing was copied.
- `templates/project.gradle.tmpl` — written out as `<dest>/java/build.gradle`; named `project.gradle.tmpl`, not `build.gradle.tmpl`, purely because the repo's `.gitignore` has a broad `*build*` glob that would otherwise silently exclude the template file itself from version control. `java` + `com.google.protobuf` (protobuf-gradle-plugin) plugins; `protobuf-java`/`protoc` pinned to `3.25.3`; `grpc-protobuf`/`grpc-stub`/`grpc-netty-shaded` pinned to `1.62.2` (compatible with protobuf 3.25.x) plus the `protoc-gen-grpc-java:1.62.2` plugin artifact and a `compileOnly org.apache.tomcat:annotations-api` (generated stub classes reference `javax.annotation.Generated`, absent from the JDK's own classpath since Java 9). `generateProtoTasks { all()*.plugins { grpc {} } }` runs the grpc plugin over *every* `.proto` in the source set, including the plain message files — harmless, since protoc/the grpc plugin emit nothing for a file with no `service` block. No explicit `sourceSets` block — protobuf-gradle-plugin's default `src/main/proto` source dir is scanned recursively, which already covers the `protofiles/` subdirectory used here.
- `templates/settings.gradle.tmpl` — static: `rootProject.name = 'harpia_generated_java'`.

## Key facts / gotchas
- **Copies, does not reference, the source `.proto` tree.** `<dest>/java/` is deliberately self-contained (no `srcDir` reaching outside its own directory) — the thread's actual motivation (`../Initiatives/multi-language-targets/thread-1-java-target/README.md` §7) is an Android app depending on a Gradle module built from this output, which needs to be portable on its own.
- **Must run after `copyBasicProtos`**, unlike J.2's original placement right after the `FileCreator` loop — J.3 needs `errorCode.proto`/`heartBeat.proto` already copied into `<dest>/proto/protofiles/` by that call. `main.py` was reordered accordingly.
- **No `HARPIA_GEN_LANG`-style backend registry exists yet** (unlike `Database/backends`) — README §3 explicitly defers designing that seam until a second language exists. `main.py` does a plain `os.environ.get("HARPIA_GEN_LANG", "cpp")` string check; `GradleAdapter` itself has no language-selection logic of its own, it just always emits Java wiring when called.
- **Stale-output pruning needs no special-casing.** `Util.util.prune_stale_outputs` already walks the *entire* `<dest>` tree matching harpia's generic `<name>_<hash>...` pattern before any adapter runs, so a renamed/removed message's stale copies under `<dest>/java/src/main/proto/protofiles/` are cleaned up for free. (`errorCode.proto`/`heartBeat.proto` aren't hash-qualified, so pruning never touches them — same as their C++-side copies.)
- protoc/`protoc-gen-grpc-java` are never invoked on the harpia generation host — they're resolved by `protobuf-gradle-plugin` the first time `gradle build` runs against the emitted project, which needs network access to Maven Central (not available inside the harpia Docker image today; genuinely a "not part of the Docker image yet" gap, not an oversight — see `UnitTests/test_java_gradle_wiring.py`'s gradle+JDK-gated integration tests).
- Every pinned version (protobuf-gradle-plugin, protobuf-java(-util)/protoc, grpc-*, protoc-gen-grpc-java, annotations-api) lives in `project.gradle.tmpl`; bumping any of them is just editing that one template file, no code change.
- `project.gradle.tmpl` also registers a `harpiaRuntimeClasspath` task (prints `sourceSets.main.runtimeClasspath.asPath`) — added so this repo's own gradle+JDK-gated integration tests (`UnitTests/_java_gradle_helpers.py`) can resolve a runnable classpath without hand-globbing exact jar paths out of the Gradle dependency cache (which breaks the moment a pinned version changes or a new transitive dependency enters the graph). Generically useful to a consumer running a generated class ad hoc, too, not test-only scaffolding.
- **`capabilities_service.proto` is deliberately never wired in** — it's the S5 message-versioning gRPC capability handshake's own service (a whole-project advertisement, not per-message), unrelated to the per-message `_Service` stubs this session wires. Whichever future session gives the Java target a capability handshake (not yet itemized in the 27-session breakdown) owns adding it.

## Why build-time codegen (decision resolved 2026-08-23, session J.1)

Two options existed: generation-time (harpia shells out to `protoc`+
`protoc-gen-grpc-java`, commits `.java` as vendored source, matching
every other stage in this repo) vs. build-time (harpia emits `.proto` +
`build.gradle` wiring, the *consumer's* Gradle build runs codegen via
`protobuf-gradle-plugin`). Chose build-time:
- Idiomatic for the Java/Gradle ecosystem this target's own motivation
  (Android fleet, `../Initiatives/multi-language-targets/thread-1-java-target/README.md`
  §7) already commits to — an Android app module's own build already
  resolves Gradle plugins this way.
- Sidesteps needing `protoc-gen-grpc-java` (a JVM-targeting native
  binary) in the harpia Docker image at all.
- Version pinning moves to the generated `build.gradle`, where a
  consumer already expects to control their protobuf/gRPC version,
  instead of requiring a harpia rebuild to bump.

**Trade-off accepted, not overlooked:** for Java specifically, codegen
timing moves to the consumer's build, unlike every other target. J.2/J.3
emit `protobuf-gradle-plugin` wiring, not a harpia-side `protoc`/`grpc_out`
shell-out; J.22 (Gradle packaging) is what actually produces the fuller
`build.gradle` J.2/J.3 need at minimum a `protobuf {}` block from.

## Touchpoints
- Called by: `main.py`, gated on `HARPIA_GEN_LANG=java`, after `copyBasicProtos`/`copyServerClientTemplates`/`copyCMakeFiles`.
- Depends on: `Util.util.write_if_different`/`copy_if_different`/`loadTemplate`, `Logger.logger`, `Errors.Error`. Consumes `MessageCreator` messages, `ProtoFile.FileCreator`'s already-written per-message output, and `copyBasicProtos`'s framework-proto copies.
- Consumed by: J.22 (Gradle packaging, the fuller build.gradle this one only partially anticipates), J.25/J.26 (Android verification — consumes `<dest>/java/` as a Gradle module for message classes and the gRPC client respectively).
