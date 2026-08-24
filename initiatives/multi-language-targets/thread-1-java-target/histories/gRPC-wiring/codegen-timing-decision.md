### Session J.1 — Codegen-timing decision + `.proto` option emission

- **Depends on:** nothing (see Receives above).
- **Decide before this session is "done," not after (`../../README.md` §4
  item 1):** codegen timing — generation-time (harpia shells out to
  `protoc`+`protoc-gen-grpc-java`, commits `.java` as vendored source,
  matching every other stage in this repo) vs. build-time (harpia emits
  `.proto` + `build.gradle`, the consumer's Gradle build runs codegen via
  `protobuf-gradle-plugin`). Leans toward build-time as more idiomatic,
  but frames it as a deliberate call, not a default — make that call
  explicitly, document it, as part of this session. Every later session
  in this group depends on the answer.
- **Deliverable:** `option java_multiple_files = true;` + `option
  java_package = "...";` added to `FileCreator.py`'s emitted `.proto`
  (Java's protoc plugin packs every message into one outer wrapper class
  by default unless this is set — small, real, easy to get wrong
  silently).
- **Out of scope:** the actual `protoc`/`grpc` invocation (J.2, J.3).
- **Tests:**
  - Unit: generated `.proto` for a multi-message file carries the new
    options and is still valid protobuf syntax.

## Decision (resolved 2026-08-23)

**Build-time codegen.** harpia emits `.proto` + a `build.gradle` wired with
`protobuf-gradle-plugin`; the *consumer's* Gradle build invokes `protoc` and
`protoc-gen-grpc-java` (both auto-fetched from Maven Central, version-pinned
in the generated `build.gradle`), not harpia at generation time.

**Why, over generation-time (the "matches every other stage" option):**
- Idiomatic for the Java/Gradle ecosystem this target's own motivation
  (`../../README.md` §7, the Android fleet) already commits to — an Android
  app module's own build already resolves Gradle plugins this way, so a
  harpia-generated Java module fits in with no build-system translation,
  the same argument `../../README.md` §2's Build/packaging row makes for
  choosing Gradle over Maven in the first place.
- Sidesteps needing `protoc-gen-grpc-java` (a JVM-targeting native binary)
  in the harpia Docker image at all — one less toolchain dependency on the
  generation host, and one that's genuinely awkward there (unlike
  `protoc`/`grpc_cpp_plugin`, which the image already carries for the C++
  target).
- Version pinning moves to the generated `build.gradle`, which is exactly
  where a consumer already expects to control their protobuf/gRPC version,
  rather than being pinned inside harpia's own Docker image and requiring a
  harpia rebuild to bump.

**Trade-off accepted, not overlooked:** this is a real behavioral difference
from every other stage in this repo (C++'s `.proto`→`.pb.{h,cc}`/gRPC stubs,
and this same file's own `.proto` emission for every other language) — those
all commit generated source at harpia generation time. For Java specifically,
codegen timing moves to the consumer's build. That divergence is the whole
reason this was flagged as a real fork instead of defaulted (`../../README.md`
§4 item 1) — accepting it here, for this stage only, is the deliberate call
this session exists to make.

**Consequence for later sessions:** J.2 (message-class generation) and J.3
(gRPC stub generation) emit `build.gradle` `protobuf-gradle-plugin` wiring,
not a harpia-side `protoc --java_out`/`--grpc_out` shell-out. J.22 (Gradle
packaging) is the session that actually produces the `build.gradle` these
depend on — J.2/J.3 need at minimum the `protobuf { protobuf {...} }` block
wired in, ahead of J.22's fuller packaging scope; flagged here so that
ordering dependency isn't lost between now and then.