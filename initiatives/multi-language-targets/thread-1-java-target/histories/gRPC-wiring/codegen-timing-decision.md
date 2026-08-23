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