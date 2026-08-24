# Thread 1 — Java as a generation target

Motivated by an existing Android fleet: Python was the abstract
per-stage-cost recommendation as of 2026-08-11, but a concrete business
need (an existing Android fleet wanting harpia-generated Java code now)
overrode that in a 2026-08-22 addendum — Python is still next in line,
not dropped. This thread scopes Java as
a full generation target, symmetric with C++; the actual motivating use
case (an Android client SDK, a *subset* of what this thread builds) is
§7 below, not a separate thread.

Session breakdown (27 sessions, one deliverable + tests each, sized to
fit a single sitting): [track-j-java-target.md](histories/track-j-java-target.md).

**Status as of 2026-08-23: J.1-J.24 landed** (gRPC-wiring, JSON, DB×2
dialects, XML, REST, SOAP, ZMQ×core+CURVE, generated tests + Gradle
packaging, and the protobuf-runtime-variant decision) — real code, real
Python-side tests, all passing in this repo's own suite; the
gradle+JDK-gated Java-side integration tests are written correctly-by-
inspection but haven't executed anywhere with a JVM toolchain yet (no JDK
in this environment or, currently, the harpia Docker image — flagged
throughout, not silently assumed passing). **J.25-J.27 (Android
verification) are written but genuinely unverified** — this environment
has no Android SDK/emulator at all, a strictly bigger gap than "no JDK."
See [`examples/android_consumer/README.md`](../../../examples/android_consumer/README.md)
for the full verification-status picture and what running it for real
would need.

---

## 1. What this thread targets, precisely

Two different things get called "Java support" and they are not the same
scope:

1. **Java as a full generation target**, symmetric with C++ (and the
   future Python target): every stage gets a Java equivalent — DB/CRUDL/
   migration, REST + SOAP servers, gRPC service impls, generated JUnit
   tests, packaging. Output is a standard JVM project (desktop/server),
   the same shape as the C++ output is a standard native project.
2. **An Android client SDK**: just the message classes, JSON
   (de)serialization, and a client that talks to a server (REST client
   and/or ZMQ) — no DB layer, no REST/SOAP server, no gRPC service impl,
   because a phone doesn't host those.

**This thread scopes (1)**, per the explicit choice made when this was
first scoped. But (2) is the actual motivating use case, so §7 below
treats it directly: an Android app is a *consumer* of a subset of what
(1) generates, not a separate build target with its own adapters.

## 2. Per-stage: what's already language-agnostic vs. what's genuinely Java-specific

Grounded in the actual current adapter implementations (re-read when
this was first scoped, not assumed from any other language's table by
analogy — a JVM-family language is not a free transfer from another
language's stdlib-heavy story).

| Stage | What it emits today (C++) | Cost to retarget to Java | Why |
|---|---|---|---|
| 0–6 (front-end) | Tokens → `Message` IR | **Free** | Unchanged — nothing here is C++-specific, same as every other target. |
| 6/7 `.proto` emission | `.proto` per message (`FileCreator.py`), then `protoc --cpp_out` | **Near-free, with one real wrinkle** | `FileCreator.py` already emits one `.proto` file per message (hash-qualified). Java's protoc plugin, unlike Python's, packs every message in one `.proto` file into a single outer wrapper class by default (`option java_outer_classname`) unless `option java_multiple_files = true;` is set — since harpia's convention is already "one message per file," `FileCreator.py` needs one new emitted line (`option java_multiple_files = true;` + `option java_package = "...";`) per `.proto`, not a structural change. Small, real, easy to get wrong silently (compiles fine either way, just nests classes differently than every other target does). |
| 13 gRPC stubs | `.proto` service → `protoc --grpc_out` stub + hand-templated impl | **Split, plus a genuine architecture fork** | Stub generation needs `protoc-gen-grpc-java` (an `io.grpc:protoc-gen-grpc-java` binary). Two real options, not one obvious answer: **(a)** mirror C++ — shell out to `protoc`+the grpc-java plugin at harpia generation time, commit the generated `.java` as vendored source, same "generation-time, vendored" story as everywhere else in this repo; **(b)** emit only the raw `.proto` + a `build.gradle` wired with the `protobuf-gradle-plugin`, and let the *consumer's* Gradle build invoke `protoc`+the grpc plugin (Gradle fetches both automatically from Maven Central, version-pinned in the build file — no toolchain-install problem on the harpia generation host at all). (b) is more idiomatic for the Java/Gradle ecosystem and sidesteps needing `protoc-gen-grpc-java` in the harpia Docker image, but it's a real behavioral difference (codegen timing moves from harpia to the consumer) that should be picked deliberately, not defaulted into. **Flagged as an open decision, see §4.** |
| 9 JSON | Thin C++ wrapper over `google::protobuf::util` | **Free-ish, same argument as Python** | `protobuf-java-util`'s `com.google.protobuf.util.JsonFormat` (`.printer()`/`.parser()`) implements the identical canonical protobuf-JSON mapping C++ and Python use. The adapter likely collapses to a thin wrapper, same shape as JsonAdapter today. |
| 10 XML | Hand-written reflection-walking runtime (`runtime/harpia_xml.h`) over `tinyxml2`, since protobuf has no built-in XML | **Real, but bounded — and actually cheaper than C++ here** | protobuf-java's reflection API (`Message.getDescriptorForType()`, `Descriptors.FieldDescriptor`, `Message.getField(fd)`/`hasField(fd)`) is directly comparable in shape to what `harpia_xml.h` walks today. Unlike C++ (which had to vendor `tinyxml2` — no XML in the C++ stdlib), Java's `javax.xml`/DOM/StAX is JDK-builtin, so the new runtime needs **zero extra dependency** — a genuine win over the C++ story, not just a port. One new runtime class + one wrapper template, same shape as today. |
| 8 DB/CRUDL/migration | SOCI-backed SQL (`Database/backends/` dialect seam + `CrudlAdapter`/`MigrationAdapter` templates) | **Real, largest piece — but the best-understood porting target** | JDBC's `PreparedStatement.setInt/setString/setLong(index, ...)` (bind) + `ResultSet.getInt/getString(column)` (extract) is a direct structural analogue of SOCI's `use()`/`into()`. `Database/model.py`'s `analyze()`/`map_fields()`/`repeated_fields()` IR is already fully language-agnostic and gets reused as-is. Drivers: `org.xerial:sqlite-jdbc` (pure JDBC, bundles native SQLite per-platform transparently — a downloaded Maven artifact, no source-vendoring needed) for SQLite; `org.postgresql:postgresql` (pure Java, **no native library at all**, unlike C++'s `libpq`) for Postgres — genuinely simpler than the C++/vcpkg story. |
| 11/12 REST/SOAP | Crow (vendored, header-only) + tinyxml2 | **Real, and a real framework-weight decision, same shape as the gRPC fork above** | Two candidates, matching Crow's "minimal, no big framework" ethos rather than Spring (wrong shape for hand-templated route registration): `com.sun.net.httpserver.HttpServer` (JDK-builtin since Java 6, **zero dependency**) or a thin third-party layer (e.g. Javalin) for nicer routing ergonomics at the cost of one dependency. Recommend the JDK-builtin one for the same reason the XML runtime picked `javax.xml` — least new dependency surface. **SOAP is cheaper than it looks**: harpia's `SoapAdapter` doesn't use a real SOAP/WS-* stack even in C++ — it hand-rolls envelope get/set/update/delete parsing over its own XML adapter. Java's SOAP story (JAX-WS removed from the JDK since 11) doesn't matter here — port the same hand-rolled envelope logic over the new Java XML runtime, no extra dependency. |
| 13 ZMQ | cppzmq (native, linked) | **Real, but smaller than C++'s own Windows story turned out to be** | `org.zeromq:jeromq` is a pure-Java reimplementation of the ZMTP wire protocol — **no JNI, no native library, no per-platform build** at all. Socket-pattern API is close enough to cppzmq that the origin-id scheme ports as the portable algorithm it already is. **Confirmed 2026-08-23 (session J.17): CURVE is supported**, pinned to `org.zeromq:jeromq:0.6.0` — see [`JavaZmqAdapter/CLAUDE.md`](../../../JavaZmqAdapter/CLAUDE.md) for the full verification (continuously maintained since 0.4.1/2017, not a one-line claim) and its one caveat (web-research-based, not yet a locally-executed handshake). |
| 14 generated tests | CTest + hand-rolled C++ assertions | **Real, mechanical** | JUnit 5 is the direct analogue of CTest/pytest, runs via Gradle's `test` task. `TestAdapter.py`'s ~8 body builders each need a Java-source-emitting counterpart; they already consume `Database.model`'s language-agnostic IR directly, so the port is per-builder mechanical, not structural. |
| Build/packaging | CMake + vendored C++ libs | **Real, different shape — but this is where the Android motivation pays off directly** | **Gradle**, not Maven — deliberately, because Gradle is what Android app modules already use. A harpia-generated Java project (or, per §7, the client-shaped subset of it) becomes a Gradle module an Android app can depend on with no build-system translation at all. |

**Bottom line:** front-end, proto emission, and JSON stay near-zero
marginal cost. XML and REST are *cheaper* here than they were for C++
(JDK-builtin XML, no framework vendoring needed). DB is the biggest
slice, same as always, and reuses the same language-agnostic IR. ZMQ is
genuinely easier than C++'s own story turned out to be (no native linking
at all). The real novelty is two **architecture forks with no single
obviously-correct answer** (§4), not per-stage translation difficulty.

## 3. Why the per-language abstraction still isn't designed here

Same reasoning that kept `Database/backends/` undesigned until Postgres
gave it a second, concrete case to diff against SQLite: one C++ data
point wasn't enough to design a `DbBackend`-style seam, and it still
isn't enough with Java as a
second data point chosen *before* Python. If Java lands before Python,
the seam gets designed off Java vs. C++ instead of Python vs. C++; either
pairing is fine, *neither single pairing* is enough — still wait for a
third data point, or at minimum treat a two-language seam as provisional
until Python exists too.

## 4. Two decisions this thread deliberately leaves open

Both come up in §2's table; naming them here so a future session doesn't
have to re-derive that they're real forks:

1. **Codegen timing for `.proto`/gRPC stubs**: generation-time (harpia
   shells out to `protoc`+`protoc-gen-grpc-java`, commits `.java` as
   vendored source — matches every other stage in this repo) vs.
   build-time (harpia emits `.proto` + `build.gradle` wiring, the
   consumer's Gradle build runs codegen via `protobuf-gradle-plugin`).
   Leans toward build-time as more idiomatic for the ecosystem, but
   that's a real behavior change worth a deliberate call, not a default.
   **Resolved 2026-08-23 (session J.1): build-time**, for the reasons
   above plus sidestepping `protoc-gen-grpc-java` in the harpia Docker
   image — see
   [`GradleAdapter/CLAUDE.md`](../../../GradleAdapter/CLAUDE.md)
   for the full rationale and its consequence for J.2/J.3/J.22.
2. **protobuf runtime variant**: full runtime (reflection-capable —
   required by both the JSON stage's `JsonFormat` and the XML stage's
   reflection walk) vs. `protobuf-javalite` (Android-oriented, smaller,
   DEX-method-count-friendly, but **not reflection-capable** —
   `JsonFormat` and a descriptor-walking XML runtime don't work against
   lite-generated classes at all). This directly determines whether an
   Android consumer (§7) gets the JSON/XML stages for free or has to
   hand-roll non-reflective codecs. Not resolved here — see §7.
   **Resolved 2026-08-23 (session J.24): full runtime**, not `javalite` —
   preserves J.4's `JsonFormat`-based JSON for Android rather than needing
   a second, non-reflective implementation, and multidex/R8 substantially
   mitigate the DEX-size pressure that originally motivated `javalite`.
   **Caveat this decision carries plainly:** not verified against a real
   Android build (no Android SDK/emulator in this environment) — see
   [histories/Android-consumption/protobuf-runtime-variant-decision.md](histories/Android-consumption/protobuf-runtime-variant-decision.md)
   for the full reasoning and what a real APK/DEX-count check would need
   to confirm.

## 5. Selector mechanism

Same shape as `HARPIA_DB_BACKEND` → `get_backend()`: thread a
`HARPIA_GEN_LANG` env var (default
`cpp`) through `main.py`, resolved once.

## 6. Slice order

J.1–J.24 (proto/gRPC, JSON, DB×2 dialects, XML, REST, SOAP, ZMQ,
tests+packaging) shipped — see the status header above. Only J.25–J.27
(Android consumption verification) remain open; see
[track-j-java-target.md](histories/track-j-java-target.md).

## 7. Android consumption — the actual motivating use case

The output of the full target (J.1–J.9) is a **standard JVM
server/library project**, the same relationship C++'s generated output
has to a native server — not something that runs on-device as-is. An
Android app is a *consumer* of a subset of it:

- **Message classes** (protobuf-java, full generated POJOs+builders) —
  fully portable, pure Java, no JNI, no reason this doesn't work on
  Android as generated.
- **JSON (de)serialization** — portable *if and only if* the full
  protobuf runtime is what got generated (§4 item 2). This is the one
  place the "full symmetric target" choice and the Android motivation can
  pull in different directions: Android best-practice more often reaches
  for `protobuf-javalite` (smaller, DEX-friendly) specifically *because*
  full apps don't usually need reflection — but harpia's own JSON/XML
  stages are built ON that reflection. An Android consumer that wants
  javalite loses `JsonFormat`/the XML runtime for free and needs
  hand-rolled non-reflective codecs instead. Not a blocker, just a real
  trade-off to make explicit before committing rather than discover after
  the fact.
- **gRPC client** — `io.grpc:grpc-android` + the `grpc-okhttp` transport
  is the standard Android-specific gRPC artifact set (full `grpc-netty`
  is a desktop/server thing); this is additive to whatever §2's gRPC-stub
  slice produces, not a replacement for it.
- **ZMQ client (JeroMQ)** — pure Java, no JNI, should run on Android
  as-is; unverified specifically on Android (vs. desktop/server JVM)
  until verified for real. Android's main-thread network I/O restriction
  is an app-architecture concern for whoever consumes this, not a harpia
  generation concern.
- **DB/CRUDL, REST/SOAP servers, gRPC service impl — not consumed
  on-device** at all under this thread's scope. `com.sun.net.httpserver`
  and JDBC drivers are desktop/server-JVM assumptions; whether they're
  even present on Android's API surface wasn't checked (flagged, not
  assumed) and doesn't matter for the consumption pattern above
  regardless, since a phone isn't meant to host these.

**This section is the one to re-read first** if a future session picks
this thread back up primarily because of the Android fleet, rather than
because Java's turn came up in the general multi-language sequence — it's
where the "full symmetric target" framing and the actual on-device use
case diverge enough to need a deliberate call (§4 item 2), not an
assumption.

## 8. Scale check

Same order of magnitude as a full language-target build generally runs —
for comparison, the `Database/` Postgres-backend seam addition (a single
focused, known-shape change) was 4 commits, ~450 lines, one afternoon; a
full language target touches the equivalent of every module in the repo,
comparable to (or larger than) the whole Postgres-backend effort (an
8-slice branch plan). Two things push it slightly larger than a Python
estimate would
have been, despite Java and Python being superficially "just another
mainstream language": (a) §4's two genuine architecture forks have no
single obviously-correct answer the way Python's choices mostly would
have (pip install X, done); (b) §7 means this thread's "done" bar isn't
just "Java target builds and passes its own generated tests" — it's also
"the Android consumption path was verified for real," which is where the
actual value is and where the actual unknowns (§4 item 2,
JeroMQ-on-Android, CURVE-on-JeroMQ) live.

## 9. Recommendation

1. §4's two open decisions are resolved (see the status header above and
   §4 itself) — nothing left to confirm before writing code.
2. Remaining work is J.25–J.27 only: an actual Android build consuming
   the generated artifacts (§7), not a documentation afterthought — it's
   the reason this thread exists. See `track-j-java-target.md`.
3. Python is still next in line after Java — this thread's existence
   doesn't mean Python no longer matters (see the 2026-08-22
   selection-history note in this file's opening paragraph).
