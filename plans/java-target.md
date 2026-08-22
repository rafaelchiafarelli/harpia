# Java as a generation target (motivated by an existing Android fleet)

> Scoping doc, not a build plan. Companion to
> [multi-language-targets.md](multi-language-targets.md) — read that doc's §2
> (per-stage cost table methodology) and §3 (why the language-abstraction seam
> isn't designed until a second concrete language exists) first; this doc
> reuses both without repeating them. It also **reorders** that doc's §5 item
> 5 ("Java stays explicitly out of scope until Python validates the
> approach"): the reason isn't that the Python analysis was wrong, it's a
> concrete business fact that analysis didn't have — an existing fleet of
> Android devices/apps that want to consume harpia-generated code today. See
> multi-language-targets.md's own addendum for the cross-reference.

## 1. What this doc targets, precisely

Two different things get called "Java support" and they are not the same
scope:

1. **Java as a full generation target**, symmetric with C++ (and the future
   Python target): every stage gets a Java equivalent — DB/CRUDL/migration,
   REST + SOAP servers, gRPC service impls, generated JUnit tests, packaging.
   Output is a standard JVM project (desktop/server), the same shape as the
   C++ output is a standard native project.
2. **An Android client SDK**: just the message classes, JSON (de)serialization,
   and a client that talks to a server (REST client and/or ZMQ) — no DB layer,
   no REST/SOAP server, no gRPC service impl, because a phone doesn't host
   those.

**This doc scopes (1)**, per the explicit choice made when this doc was
started. But (2) is the actual motivating use case, so §7 below treats it
directly: an Android app is a *consumer* of a subset of what (1) generates,
not a separate build target with its own adapters. That distinction matters
concretely — see §7's runtime-variant tension — so don't skip it because (1)
was the pick.

## 2. Per-stage: what's already language-agnostic vs. what's genuinely Java-specific

Same methodology as multi-language-targets.md §2, grounded in the actual
current adapter implementations (re-read for this doc, not assumed from the
Python table by analogy — a JVM-family language is not a free transfer from
Python's stdlib-heavy story).

| Stage | What it emits today (C++) | Cost to retarget to Java | Why |
|---|---|---|---|
| 0–6 (front-end) | Tokens → `Message` IR | **Free** | Unchanged — nothing here is C++-specific, same as every other target. |
| 6/7 `.proto` emission | `.proto` per message (`FileCreator.py`), then `protoc --cpp_out` | **Near-free, with one real wrinkle** | `FileCreator.py` already emits one `.proto` file per message (hash-qualified). Java's protoc plugin, unlike Python's, packs every message in one `.proto` file into a single outer wrapper class by default (`option java_outer_classname`) unless `option java_multiple_files = true;` is set — since harpia's convention is already "one message per file," `FileCreator.py` needs one new emitted line (`option java_multiple_files = true;` + `option java_package = "...";`) per `.proto`, not a structural change. Small, real, easy to get wrong silently (compiles fine either way, just nests classes differently than every other target does). |
| 13 gRPC stubs | `.proto` service → `protoc --grpc_out` stub + hand-templated impl | **Split, plus a genuine architecture fork** | Stub generation needs `protoc-gen-grpc-java` (an `io.grpc:protoc-gen-grpc-java` binary). Two real options, not one obvious answer: **(a)** mirror C++ — shell out to `protoc`+the grpc-java plugin at harpia generation time, commit the generated `.java` as vendored source, same "generation-time, vendored" story as everywhere else in this repo; **(b)** emit only the raw `.proto` + a `build.gradle` wired with the `protobuf-gradle-plugin`, and let the *consumer's* Gradle build invoke `protoc`+the grpc plugin (Gradle fetches both automatically from Maven Central, version-pinned in the build file — no toolchain-install problem on the harpia generation host at all). (b) is more idiomatic for the Java/Gradle ecosystem and sidesteps needing `protoc-gen-grpc-java` in the harpia Docker image, but it's a real behavioral difference (codegen timing moves from harpia to the consumer) that should be picked deliberately, not defaulted into. **Flagged as an open decision, see §4.** |
| 9 JSON | Thin C++ wrapper over `google::protobuf::util` | **Free-ish, same argument as Python** | `protobuf-java-util`'s `com.google.protobuf.util.JsonFormat` (`.printer()`/`.parser()`) implements the identical canonical protobuf-JSON mapping C++ and Python use. The adapter likely collapses to a thin wrapper, same shape as JsonAdapter today. |
| 10 XML | Hand-written reflection-walking runtime (`runtime/harpia_xml.h`) over `tinyxml2`, since protobuf has no built-in XML | **Real, but bounded — and actually cheaper than C++ here** | protobuf-java's reflection API (`Message.getDescriptorForType()`, `Descriptors.FieldDescriptor`, `Message.getField(fd)`/`hasField(fd)`) is directly comparable in shape to what `harpia_xml.h` walks today. Unlike C++ (which had to vendor `tinyxml2` — no XML in the C++ stdlib), Java's `javax.xml`/DOM/StAX is JDK-builtin, so the new runtime needs **zero extra dependency** — a genuine win over the C++ story, not just a port. One new runtime class + one wrapper template, same shape as today. |
| 8 DB/CRUDL/migration | SOCI-backed SQL (`Database/backends/` dialect seam + `CrudlAdapter`/`MigrationAdapter` templates) | **Real, largest piece — but the best-understood porting target, same as Python's analysis** | JDBC's `PreparedStatement.setInt/setString/setLong(index, ...)` (bind) + `ResultSet.getInt/getString(column)` (extract) is a direct structural analogue of SOCI's `use()`/`into()`. `Database/model.py`'s `analyze()`/`map_fields()`/`repeated_fields()` IR is already fully language-agnostic and gets reused as-is. Drivers: `org.xerial:sqlite-jdbc` (pure JDBC, bundles native SQLite per-platform transparently — a downloaded Maven artifact, no source-vendoring needed) for SQLite; `org.postgresql:postgresql` (pure Java, **no native library at all**, unlike C++'s `libpq`) for Postgres — genuinely simpler than the C++/vcpkg story this session just fought through. |
| 11/12 REST/SOAP | Crow (vendored, header-only) + tinyxml2 | **Real, and a real framework-weight decision, same shape as the gRPC fork above** | Two candidates, matching Crow's "minimal, no big framework" ethos rather than Spring (wrong shape for hand-templated route registration — opinionated, heavyweight, and its DI/annotation model doesn't map onto how harpia emits routes today): `com.sun.net.httpserver.HttpServer` (JDK-builtin since Java 6, **zero dependency**, low-level enough that harpia's own generated routing code fills the gap the same way it already does for Crow) or a thin third-party layer (e.g. Javalin) for nicer routing ergonomics at the cost of one dependency. Recommend the JDK-builtin one for the same reason the XML runtime picked `javax.xml` — least new dependency surface. **SOAP is cheaper than it looks**: harpia's `SoapAdapter` doesn't use a real SOAP/WS-* stack even in C++ — it hand-rolls envelope get/set/update/delete parsing over its own XML adapter (see `Database/CLAUDE.md`). Java's SOAP story (JAX-WS removed from the JDK since 11) doesn't matter here at all — port the same hand-rolled envelope logic over the new Java XML runtime, no extra dependency. |
| 13 ZMQ | cppzmq (native, linked) | **Real, but smaller than C++'s own Windows story turned out to be** | `org.zeromq:jeromq` is a pure-Java reimplementation of the ZMTP wire protocol — **no JNI, no native library, no per-platform build** at all, which sidesteps the entire class of problem this session just spent hours on (vcpkg, MSVC, antivirus false positives) for the C++ Postgres backend. Socket-pattern API (`ZMQ.Context`/`ZMQ.Socket`, PUSH/PULL/PUB/SUB, `bind`/`connect`/`send`/`recv`) is close enough to cppzmq that the origin-id scheme (`_origin_id`, `runtime_origin_id()` — see `ZmqAdapter/CLAUDE.md`) ports as the portable algorithm it already is. **One unconfirmed fact, flagged rather than assumed**: JeroMQ claims CURVE support in recent releases, but this hasn't been verified against a pinned version — needs a real check before the CURVE slice is scoped, the same discipline this repo applied to the SOCI::PostgreSQL alias question before assuming an answer. |
| 14 generated tests | CTest + hand-rolled C++ assertions | **Real, mechanical, same shape as Python's ~8-builder estimate** | JUnit 5 is the direct analogue of CTest/pytest, runs via Gradle's `test` task out of the box. `TestAdapter.py`'s ~8 body builders (`_db_body`/`_json_body`/`_ar_body`/`_am_body`/`_xml_body`/`_rest_body`/`_soap_body`/`_simple_body`) each need a Java-source-emitting counterpart; they already consume `Database.model`'s language-agnostic IR directly, so the port is per-builder mechanical, not structural. |
| Build/packaging | CMake + vendored C++ libs | **Real, different shape — but this is where the Android motivation pays off directly** | **Gradle**, not Maven — deliberately, because Gradle is what Android app modules already use. A harpia-generated Java project (or, per §7, the client-shaped subset of it) becomes a Gradle module an Android app can depend on with no build-system translation at all. Combined with option (b) in the gRPC row above (`protobuf-gradle-plugin` driving codegen at consumer-build-time), this is arguably a *better* story than either C++'s vendoring or Python's `pip install` — Gradle handles the `protoc`/grpc-plugin binary fetch and version pin declaratively. |

**Bottom line, same shape as the Python table's conclusion:** front-end,
proto emission, and JSON stay near-zero marginal cost. XML and REST are
*cheaper* here than they were for C++ (JDK-builtin XML, no framework
vendoring needed). DB is the biggest slice, same as always, and reuses the
same language-agnostic IR. ZMQ is genuinely easier than C++'s own story
turned out to be (no native linking at all). The real novelty is two
**architecture forks with no single obviously-correct answer** (§4), not
per-stage translation difficulty — which is a different kind of risk than
Python's plan carried, worth naming explicitly rather than glossing over.

## 3. Why the per-language abstraction still isn't designed here

Unchanged from multi-language-targets.md §3: one C++ data point wasn't
enough to design a `DbBackend`-style seam, and it still isn't enough with
Java as a second data point chosen *before* Python, for the same reason —
Java's actual shape (this doc's §2) needs to exist for real before any
seam gets extracted, not guessed from a table. If Java lands before Python,
the seam gets designed off Java vs. C++ instead of Python vs. C++; either
pairing is fine, *neither single pairing* is enough — still wait for a
third data point, or at minimum treat a two-language seam as provisional
until the pairing that's actually missing (Python) exists too.

## 4. Two decisions this doc deliberately leaves open

Both come up in §2's table; naming them here so a future session doesn't
have to re-derive that they're real forks rather than picking one silently
and finding out later it was the wrong shape (the `DbBackend` lesson,
applied to decision-making itself, not just architecture):

1. **Codegen timing for `.proto`/gRPC stubs**: generation-time (harpia shells
   out to `protoc`+`protoc-gen-grpc-java`, commits `.java` as vendored
   source — matches every other stage in this repo) vs. build-time (harpia
   emits `.proto` + `build.gradle` wiring, the consumer's Gradle build runs
   codegen via `protobuf-gradle-plugin`). Leans toward build-time as more
   idiomatic for the ecosystem, but that's a real behavior change (codegen
   moves out of harpia's own pipeline) worth a deliberate call, not a default.
2. **protobuf runtime variant**: full runtime (reflection-capable — required
   by both the JSON stage's `JsonFormat` and the XML stage's reflection walk)
   vs. `protobuf-javalite` (Android-oriented, smaller, DEX-method-count-
   friendly, but **not reflection-capable** — `JsonFormat` and a
   descriptor-walking XML runtime don't work against lite-generated classes
   at all). This directly determines whether an Android consumer (§7) gets
   the JSON/XML stages for free or has to hand-roll non-reflective codecs.
   Full-runtime is the only option that keeps §2's "near-free" claims for
   JSON/XML true; lite-runtime is the one real Android apps more often
   reach for. Not resolved here — see §7.

## 5. Selector mechanism

Same shape as `HARPIA_DB_BACKEND` → `get_backend()` (`main.py:147-149`,
`Database/backends/__init__.py`) and as multi-language-targets.md §4
proposed for Python: thread a `HARPIA_GEN_LANG` env var (default `cpp`)
through `main.py`, resolved once. Each adapter call becomes conditional on
the target language — or, once a second language (Java or Python,
whichever lands first) makes the real shape visible, a `get_lang_backend()`
registry mirroring `Database/backends/__init__.py`'s pattern (see §3 on
why that's not designed yet).

## 6. Slice order

Mirrors multi-language-targets.md §6 item 3's Python order — same
dependency shape applies regardless of which language is second — adjusted
for this doc's two open decisions:

1. `protoc --java_out` + `--grpc_out` wiring, including the
   `java_multiple_files`/`java_package` proto-option addition (§2) and a
   decision on §4 item 1 (codegen timing) before this slice is considered
   done, not after.
2. JSON pass-through (`JsonFormat`).
3. DB/CRUDL/migration — biggest slice, reuses `Database/model.py`'s IR
   directly, SQLite (`org.xerial:sqlite-jdbc`) first, Postgres
   (`org.postgresql:postgresql`) later, same order the C++ Postgres backend
   itself shipped in (`postgres-migration.md`).
4. XML runtime (`javax.xml`-based, no vendored dependency).
5. REST/SOAP (`com.sun.net.httpserver.HttpServer`, hand-rolled SOAP envelope
   over the new XML runtime).
6. ZMQ (JeroMQ) — confirm the CURVE-support question from §2 before that
   sub-slice, not during it.
7. Generated tests (JUnit 5) + packaging (Gradle) + docs.
8. Only then, §7's Android-consumption slice: decide §4 item 2 (runtime
   variant) for real, against an actual Android build, not a guess.

## 7. Android consumption — the actual motivating use case

The output of §1–6 above is a **standard JVM server/library project**, the
same relationship C++'s generated output has to a native server — not
something that runs on-device as-is. An Android app is a *consumer* of a
subset of it:

- **Message classes** (protobuf-java, full generated POJOs+builders) — fully
  portable, pure Java, no JNI, no reason this doesn't work on Android as
  generated.
- **JSON (de)serialization** — portable *if and only if* the full protobuf
  runtime is what got generated (§4 item 2). This is the one place the "full
  symmetric target" choice and the Android motivation can pull in different
  directions: Android best-practice more often reaches for
  `protobuf-javalite` (smaller, DEX-friendly) specifically *because* full
  apps don't usually need reflection — but harpia's own JSON/XML stages are
  built ON that reflection. An Android consumer that wants javalite loses
  `JsonFormat`/the XML runtime for free and needs hand-rolled non-reflective
  codecs instead. Not a blocker, just a real trade-off to make explicit
  before committing rather than discover after the fact.
- **gRPC client** — `io.grpc:grpc-android` + the `grpc-okhttp` transport is
  the standard Android-specific gRPC artifact set (full `grpc-netty` is a
  desktop/server thing); this is additive to whatever §2's gRPC-stub slice
  produces, not a replacement for it.
- **ZMQ client (JeroMQ)** — pure Java, no JNI, should run on Android as-is;
  unverified specifically on Android (vs. desktop/server JVM) the same way
  everything in this doc that hasn't been build-verified gets flagged rather
  than assumed. Android's main-thread network I/O restriction is an
  app-architecture concern for whoever consumes this, not a harpia
  generation concern.
- **DB/CRUDL, REST/SOAP servers, gRPC service impl — not consumed on-device**
  at all under this doc's scope. `com.sun.net.httpserver` and JDBC drivers
  are desktop/server-JVM assumptions; whether they're even present on
  Android's API surface wasn't checked for this doc (flagged, not assumed)
  and doesn't matter for the consumption pattern above regardless, since a
  phone isn't meant to host these.

**This section is the one to re-read first** if a future session picks this
doc back up primarily because of the Android fleet, rather than because
Java's turn came up in the general multi-language sequence — it's where the
"full symmetric target" framing and the actual on-device use case diverge
enough to need a deliberate call (§4 item 2), not an assumption.

## 8. Scale check

Same order of magnitude as multi-language-targets.md §5's Python estimate —
a multi-session epic, comparable to (or larger than) the Postgres-backend
effort. Two things push it slightly larger than the Python estimate rather
than smaller, despite Java and Python being superficially "just another
mainstream language": (a) §4's two genuine architecture forks have no
single obviously-correct answer the way Python's choices mostly did (pip
install X, done); (b) §7 means this doc's "done" bar isn't just "Java target
builds and passes its own generated tests" the way Python's is — it's also
"the Android consumption path was verified for real," which is where the
actual value is and where the actual unknowns (§4 item 2, JeroMQ-on-Android,
CURVE-on-JeroMQ) live.

## 9. Recommendation

1. Confirm §4's two open decisions before writing any code — they change
   the shape of multiple slices, not just one line each.
2. Slice per §6, same discipline as `postgres-migration.md`'s branch plan:
   each slice lands independently, leaves C++ untouched and green, verified
   against its own equivalent of the golden-file suite before the next slice
   starts.
3. Treat §7 as a real slice with its own acceptance bar (an actual Android
   build consuming the generated artifacts), not a documentation afterthought
   tacked onto the end — it's the reason this doc exists.
4. Re-affirm multi-language-targets.md §5 item 5 for whichever language
   *doesn't* go second: if Java lands first, Python is still next in line
   for the reasons already given there — this doc's reordering is scoped to
   "Java before Python," not "Python no longer matters."
