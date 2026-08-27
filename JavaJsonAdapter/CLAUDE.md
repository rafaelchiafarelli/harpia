# JavaJsonAdapter — Java target: JSON pass-through (one shared runtime, no per-message generation)

**Pipeline role:** Java-target Stage 9 equivalent (session J.4, `Initiatives/multi-language-targets/thread-1-java-target`). Ships a single hand-written Java class wrapping `protobuf-java-util`'s `com.google.protobuf.util.JsonFormat` — the same canonical protobuf-JSON mapping the C++ (`JsonAdapter`) and future Python targets use.
**Entry point (from main.py):** gated behind `HARPIA_GEN_LANG=java` (default `cpp`, unaffected), called right after `GradleAdapter` in the same block: `JavaJsonAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()`. Returns `None` or an `Error` (non-fatal; main.py logs it).
**Inputs → Outputs:** consumes message objects only to decide whether there's anything to generate for (`Errors.Types.NOTHING_TO_REPORT` if `messages` is empty) — the runtime class itself is message-agnostic. Emits exactly one file: `<dest>/java/src/main/java/com/harpia/runtime/json/HarpiaJson.java`.

## Files
- `JavaJsonAdapter.py` — `Process()` copies (`copy_if_different`) `runtime/HarpiaJson.java` into `<dest>/java/src/main/java/com/harpia/runtime/json/`. No loop over messages, no per-message rendering — see "Why no per-message wrapper" below.
- `runtime/HarpiaJson.java` — hand-written (NOT generated, same status as `XmlAdapter/runtime/harpia_xml.h` on the C++ side), copied verbatim. `package com.harpia.runtime.json;` (deliberately NOT `com.harpia.generated`, the flat package every protoc-generated message class lives in — keeps this hand-written class from ever colliding with a message named e.g. `HarpiaJson`). Three static methods: `String toJson(Message msg)`, `<T extends Message.Builder> T fromJson(String json, T builder)` (throws `InvalidProtocolBufferException`, tolerant of unrecognized keys — same forward-compatibility stance as the C++/XML parse-boundary hardening, see `ProtoFile/CLAUDE.md`'s `optional` note), `boolean isValidJson(String json, Message.Builder prototype)` (clones `prototype` internally so the caller's own builder is never mutated by a probe call).

## Why no per-message wrapper (unlike C++'s JsonAdapter)
C++'s `JsonAdapter` emits one `_json.h` per message, each a thin wrapper typed to that one message's C++ class, even though the underlying `google::protobuf::util::MessageToJsonString`/`JsonStringToMessage` are already generic over any `google::protobuf::Message` — the per-message wrapper exists purely for typed-call ergonomics (`to_json(myPrinceMsg, &out)` reads slightly nicer than the fully-generic call), not because the underlying API needs it.

In Java, every protoc-generated message class already implements the common `com.google.protobuf.Message`/`Message.Builder` interfaces, and Java's own subtype polymorphism gives the exact same typed-call ergonomics a generic method already provides (`HarpiaJson.toJson(myPrinceMsg)` — no per-type overload needed, `Message` accepts any subtype directly). Generating N near-identical per-message wrapper classes here would be pure boilerplate with zero functional or ergonomic benefit over one shared class — the repo's own "no half-finished implementations / don't add abstractions beyond what's needed" discipline argues against it, not for parity-for-parity's-sake with the C++ shape.

## Why the full protobuf-java runtime, not `protobuf-javalite` (decision resolved 2026-08-23, session J.24; confirmed against a real Android build 2026-08-24)

This class (and `JavaXmlAdapter`'s reflection-based runtime) only works
at all against protoc's full-runtime Java output — `javalite`-generated
classes have no `getDescriptorForType()`/reflection API, so `JsonFormat`
can't operate on them. Since the Android consumption path
(`HarpiaTest/app_example/android_consumer`) depends on this class, the choice of
protobuf runtime variant was a real fork worth deciding deliberately:
Android best-practice often reaches for `javalite` specifically because
most apps don't need reflection, and it's smaller/DEX-friendlier — but
picking it here would mean building a second, non-reflective JSON/XML
implementation just for Android, an ongoing maintenance cost, not a
one-time swap. Chose the full runtime instead: multidex (API 21+) and R8
full-mode shrinking substantially mitigate the DEX-size pressure that
originally motivated `javalite` in the mid-2010s, and nothing in the
actual motivating use case (an existing Android fleet wanting parity with
the full target) named DEX size as a real constraint. Confirmed against a
real build, not just reasoned: `HarpiaTest/app_example/android_consumer`'s
`assembleRelease` (R8 enabled) produces ~105,822 methods across two dex
files (over the 65,536 single-dex limit) — multidex activates, and does
so cleanly. `GradleAdapter/templates/project.gradle.tmpl` already
depended on `com.google.protobuf:protobuf-java` (full runtime) since J.2;
this decision confirmed extending that choice to Android rather than
introducing a second, Android-specific protobuf runtime.

## Key facts / gotchas
- Depends on `protobuf-java-util`, wired into `build.gradle` by `GradleAdapter` (`GradleAdapter/templates/project.gradle.tmpl`), kept in lockstep with the `protobuf-java` version.
- `toJson` wraps the checked `InvalidProtocolBufferException` `JsonFormat.printer().print()` can throw into an unchecked `IllegalStateException` — unreachable in practice for a harpia-generated message (that exception is specific to a malformed `Any` payload, and harpia never emits `Any` fields), so forcing every caller to handle a checked exception for a case that can't happen would be exactly the kind of unnecessary defensiveness the repo's own conventions steer away from.
- Return-type/exception shape deliberately does NOT mirror C++'s boolean-return-plus-out-param style (`bool to_json(msg, std::string* out)`) — that's a C++ idiom (no natural multi-return, prefers status codes), not something worth porting into Java, where returning the value directly and throwing on the one real failure mode is the idiomatic shape.

## Touchpoints
- Called by: `main.py`, gated on `HARPIA_GEN_LANG=java`, right after `GradleAdapter` in the same conditional block.
- Depends on: `Util.util.copy_if_different`, `Logger.logger`, `Errors.Error`. The runtime class itself depends only on `protobuf-java`/`protobuf-java-util` (declared in `GradleAdapter`'s `build.gradle`), never on this repo's Python code at runtime.
- Consumed by: any Java-target REST/SOAP session that needs JSON (X-content-negotiation, mirroring `Database/RestAdapter.py`'s C++ story) — not yet scoped in the 27-session breakdown by name.
