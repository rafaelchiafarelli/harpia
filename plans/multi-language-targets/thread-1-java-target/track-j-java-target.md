# Java target — session breakdown

Session IDs below use a `J.<n>` prefix (J for Java) purely as a compact
label — not a reference to `harpia_medical_master_plan.md`'s track
lettering. This plan is standalone and general-purpose, not
medical-devices-specific (see `../../README.md`); the one place it
touches that other plan is a real, narrow link, called out in Receives/
Gives below, not a shared identity.

**Corrected 2026-08-23 (was stale):** this used to say Python, per
`multi-language-targets.md`'s original recommendation. This folder's own
`../README.md` §4 records that **Java** was picked instead as the actual
second target — an existing Android fleet wants harpia-generated Java
code now, a concrete business reason, not a re-litigation of the abstract
Python-vs-Java cost comparison.

**Re-graded 2026-08-23: this file originally reused `java-target.md`'s
own 8-slice order almost as-is** (only splitting DB by dialect and
REST/SOAP by transport) — each "slice" bundled several independent
deliverables into one sitting (e.g. the old "DB/CRUDL/migration, SQLite"
slice bundled scaffolding, bind/extract, and full CRUDL together).
Rebuilt below at a finer grain: one deliverable, its own tests, sized to
fit a single sitting — 27 sessions instead of 10. Consistent with this
track's own scale check (`../README.md` §6): comparable to, or larger
than, the Postgres-backend effort, which itself was an 8-slice branch
plan before anyone tried to fit it into single-sitting sessions.

## Receives (must be done before this track starts)

- **Nothing from another plan.** This is general-purpose harpia
  capability, not gated on the medical-compliance plan's Foundation.
  Stages 0–6 (front-end) and `.proto` emission are already
  language-agnostic, shipped infrastructure this track reuses as-is —
  see `../README.md` §2.
- **Conditional, not a hard blocker:** if a consumer wants the Java
  target to be compliance-aware (respect `risk_class`/`phi` the way the
  C++ target does once `harpia_medical_master_plan.md`'s Foundation
  lands), that's an additional concern layered on top by
  `plans/medical_devices/schedule/thread-4-platform-infra/track-j-java-target.md`'s
  thin pointer, not a precondition for the sessions below.

## Gives (what "done" means here, consumed by whom)

- A full, symmetric Java generation target (Stages 8–14 emitters) plus a
  verified Android-consumption path (message classes, JSON, gRPC/ZMQ
  clients) for the fleet that actually motivates this work.
- **Consumed by:** the external Android fleet driving this work.
  `harpia_medical_master_plan.md`'s Track J references this as the real
  session breakdown rather than duplicating it — see that plan's own
  thin pointer file.

## Files this track touches

- New per-language emitter directories, mirroring `Database/`,
  `JsonAdapter/`, etc. **Flag:** neither `../README.md` nor this file
  commits to specific new directory names (e.g. a `JavaDatabase/`-shaped
  package) — not guessing names ahead of the first session actually
  creating them.

---

## Group: `.proto`/gRPC wiring (J.1–J.3)

### Session J.1 — Codegen-timing decision + `.proto` option emission

- **Depends on:** nothing (see Receives above).
- **Decide before this session is "done," not after (`../README.md` §4
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

### Session J.3 — `protoc --grpc_out` wiring (stub generation)

- **Depends on:** J.2 merged.
- **Deliverable:** gRPC stub generation per J.1's timing — either
  `protoc-gen-grpc-java` invoked at generation time, or the
  `protobuf-gradle-plugin` wiring extended to also run the gRPC plugin.
- **Tests:**
  - Integration: generated gRPC stub compiles and links against J.2's
    message classes.

## Group: JSON (J.4)

### Session J.4 — JSON pass-through

- **Depends on:** J.2 merged.
- **Deliverable:** thin wrapper over `protobuf-java-util`'s
  `com.google.protobuf.util.JsonFormat` — same canonical protobuf-JSON
  mapping C++/Python use.
- **Tests:**
  - Unit: JSON round trip matches the canonical mapping, including a
    field name that differs under protobuf's default camelCase mapping.

## Group: DB/CRUDL — SQLite (J.5–J.7)

### Session J.5 — DB package scaffolding + JDBC bind/extract primitives

- **Depends on:** J.2 merged.
- **Deliverable:** new Java DB package reusing `Database/model.py`'s
  language-agnostic `analyze()`/`map_fields()`/`repeated_fields()` IR
  as-is; JDBC bind/extract (`PreparedStatement.setInt/setString/setLong`
  / `ResultSet.getInt/getString`) as the structural analogue of SOCI's
  `use()`/`into()`; `org.xerial:sqlite-jdbc` driver (pure JDBC, bundles
  native SQLite per-platform, no source-vendoring needed).
- **Out of scope:** CRUDL operations themselves (J.6); migration support
  (flagged out of scope below, not part of this track's first pass).
- **Tests:**
  - Unit: bind/extract round trip per supported type.

### Session J.6 — CRUDL implementation, SQLite

- **Depends on:** J.5 merged.
- **Deliverable:** create/read/update/delete/list operations on SQLite,
  built on J.5's bind/extract primitives.
- **Tests:**
  - Integration: full CRUDL cycle against SQLite.

### Session J.7 — SQLite round-trip acceptance gate

- **Depends on:** J.6 merged.
- **Deliverable:** nothing new — closes the loop, verifying the full
  write/read/CRUDL surface built in J.5–J.6 works together end to end.
- **Tests:**
  - Integration: write → persist → restart process → read; confirm
    values match, mirroring the C++ target's own CRUDL golden tests
    (14.1/14.2).
- **Acceptance gate:** this session is the acceptance gate.

**Flagged, not scoped here:** schema-evolution/migration support is
explicitly **out of scope for this track's first pass** — `java-target.md`'s
original per-stage table didn't call it out as day-one scope, and adding
it here would be inventing scope the source material didn't commit to.
Follow-on work, if needed.

## Group: DB/CRUDL — Postgres (J.8–J.9)

### Session J.8 — Postgres driver wiring

- **Depends on:** J.7 merged — reuses J.5's backend seam.
- **Deliverable:** `org.postgresql:postgresql` driver (pure Java, no
  native library at all, unlike C++'s `libpq`) wired into the same
  bind/extract seam J.5 established.
- **Tests:**
  - Unit: bind/extract round trip per supported type, against Postgres'
    JDBC driver specifically (type-mapping differences from SQLite, if
    any, surface here).

### Session J.9 — Postgres round-trip acceptance gate

- **Depends on:** J.8 merged.
- **Deliverable:** nothing new — closes the loop for Postgres.
- **Tests:**
  - Integration: full CRUDL cycle against a real `postgres` container,
    same posture as the C++ Postgres-on-Windows resolution.
- **Acceptance gate:** this session is the acceptance gate.

## Group: XML runtime (J.10–J.11)

### Session J.10 — XML write path (`to_xml`)

- **Depends on:** J.2 merged.
- **Deliverable:** a reflection-walking serialization runtime over
  protobuf-java's reflection API (`Message.getDescriptorForType()`,
  `Descriptors.FieldDescriptor`, `Message.getField(fd)`/`hasField(fd)`),
  directly comparable in shape to `harpia_xml.h`. Uses JDK-builtin
  `javax.xml`/DOM/StAX — zero extra dependency, genuinely cheaper here
  than the C++ story (which had to vendor `tinyxml2`).
- **Out of scope:** the read path (J.11).
- **Tests:**
  - Unit: XML serialization for a message with nested/repeated fields,
    presence-gated singular-field emission matching the C++ runtime's
    `has_presence()` behavior (see `XmlAdapter/CLAUDE.md` for why that
    check matters — the C++ runtime gates singular-field emission on
    `HasField` for exactly this reason).

### Session J.11 — XML read path (`from_xml`)

- **Depends on:** J.10 merged.
- **Deliverable:** the corresponding deserialization path, reusing J.10's
  reflection-walking runtime.
- **Tests:**
  - Integration: round-trip a message with nested/repeated/absent-vs-
    default-valued fields through `to_xml`→`from_xml`, confirming
    presence is preserved, not just values.

## Group: REST (J.12–J.14)

### Session J.12 — REST routing scaffolding

- **Depends on:** J.2 merged.
- **Deliverable:** routing on JDK-builtin `com.sun.net.httpserver.HttpServer`
  (zero dependency, low-level enough that harpia's generated routing code
  fills the gap the same way it does for Crow today) — recommended over a
  third-party layer like Javalin for the same "least new dependency
  surface" reasoning the XML runtime used. Credential-gate port (the
  `X-User`/`X-Pswd` check) from `Database/RestAdapter.py`.
- **Out of scope:** the CRUDL handlers themselves (J.13).
- **Tests:**
  - Unit: credential gate accepts/rejects per the same rules as the C++
    implementation.

### Session J.13 — REST CRUDL handlers

- **Depends on:** J.12 merged; J.6 (SQLite CRUDL) merged.
- **Deliverable:** REST handlers wired to J.6's DB layer — create/read/
  update/delete/list over HTTP.
- **Tests:**
  - Integration: live REST CRUDL calls against the generated Java server.

### Session J.14 — REST acceptance gate

- **Depends on:** J.13 merged.
- **Deliverable:** nothing new — closes the loop for REST.
- **Acceptance gate:** live REST CRUDL cycle matches the C++ target's
  behavior for the same schema.

## Group: SOAP (J.15–J.16)

### Session J.15 — SOAP envelope parsing

- **Depends on:** J.10, J.11 (XML runtime), J.12 (HTTP server) merged.
- **Deliverable:** the same hand-rolled envelope get/set/update/delete
  parsing `Database/SoapAdapter.py` already does in C++ (harpia's SOAP
  was never a real SOAP/WS-* stack even there — see `Database/CLAUDE.md`),
  ported over the new Java XML runtime. Java's SOAP story (JAX-WS removed
  from the JDK since 11) doesn't matter here — no extra dependency needed.
- **Tests:**
  - Unit: envelope parsing for each operation (get/set/update/delete).

### Session J.16 — SOAP acceptance gate

- **Depends on:** J.15 merged.
- **Tests:**
  - Integration: live SOAP envelope calls against the generated Java
    server, same shape as the existing C++ SOAP tests.
- **Acceptance gate:** this session is the acceptance gate.

## Group: ZMQ (J.17–J.20)

### Session J.17 — Confirm JeroMQ CURVE support

- **Depends on:** nothing (pure verification, can run any time).
- **Deliverable:** a confirmed answer, against a pinned JeroMQ version,
  to whether CURVE is actually supported — `../README.md` §2 flags this
  as an unconfirmed claim, same discipline this repo applied to the
  SOCI::PostgreSQL alias question before assuming an answer. Blocks J.19,
  nothing else.
- **Tests:** the verification itself — a minimal CURVE handshake against
  the pinned JeroMQ version, pass/fail.

### Session J.18 — ZMQ core (no CURVE)

- **Depends on:** J.2 merged.
- **Deliverable:** `org.zeromq:jeromq` (pure-Java ZMTP reimplementation —
  no JNI, no native library, no per-platform build) wired for PUSH/PULL/
  PUB/SUB; the origin-id scheme (`_origin_id`, `runtime_origin_id()`)
  ports as the portable algorithm it already is.
- **Out of scope:** CURVE (J.19).
- **Tests:**
  - Integration: client/server ZMQ demo, mirroring the existing C++ one.

### Session J.19 — CURVE-secured ZMQ variant

- **Depends on:** J.17 (confirmed CURVE support) and J.18 merged. If J.17
  found CURVE unsupported on the pinned version, this session doesn't
  proceed as scoped — flag and re-plan rather than force it.
- **Deliverable:** CURVE-secured variant of J.18's transport.
- **Tests:**
  - Integration: CURVE-enabled client/server exchange.

### Session J.20 — ZMQ acceptance gate

- **Depends on:** J.18 merged (J.19 if it landed).
- **Acceptance gate:** ZMQ demo matches the C++ target's behavior for the
  same schema, CURVE-enabled and not.

## Group: Generated tests + packaging (J.21–J.23)

### Session J.21 — JUnit test generation

- **Depends on:** J.6 (or further DB work), J.4, J.10/J.11 merged — needs
  real emitters to generate meaningful tests against.
- **Deliverable:** JUnit 5 test generation — a Java-source-emitting
  counterpart for each of `TestAdapter.py`'s ~8 body builders
  (`_db_body`/`_json_body`/`_ar_body`/`_am_body`/`_xml_body`/`_rest_body`/
  `_soap_body`/`_simple_body`), mechanical per-builder since they already
  consume `Database.model`'s language-agnostic IR directly — genuinely
  one deliverable despite the ~8 sub-parts, since each is a stamp of the
  same pattern, not independent design work.
- **Tests:** the generated JUnit tests running successfully via Gradle's
  `test` task, once J.22 exists, is this session's own acceptance check
  (verified together with J.23, not duplicated here).

### Session J.22 — Gradle packaging

- **Depends on:** J.2 merged (needs message classes to package).
- **Deliverable:** Gradle packaging (not Maven — deliberately, since
  Gradle is what Android app modules already use): `build.gradle`
  template, dependency declarations for whichever of J.1–J.21's libraries
  the generated project actually uses.
- **Tests:**
  - Integration: `gradle build` succeeds on a minimal generated project.

### Session J.23 — Full generate → build → run demo + golden baseline

- **Depends on:** J.21, J.22 merged (and, practically, most of the
  emitter groups above — this is the track's integration point).
- **Deliverable:** nothing new — proves the whole surface works together.
- **Tests:**
  - Integration: full generate → `gradle build` → run demo, Java target,
    mirroring the existing C++ client/server demo.
- **Acceptance gate:** establishes its own golden-snapshot baseline
  (first of its kind for this target).

## Group: Android consumption (J.24–J.27)

### Session J.24 — Protobuf runtime variant decision

- **Depends on:** J.4 (JSON), J.10/J.11 (XML) merged — the decision needs
  to weigh what those two would lose under `javalite`.
- **Decide for real, against an actual Android build, not a guess
  (`../README.md` §4 item 2):** full runtime (reflection-capable,
  required by J.4's `JsonFormat` and J.10/J.11's XML runtime) vs.
  `protobuf-javalite` (Android-oriented, DEX-friendly, not reflection-
  capable — loses JSON/XML for free if picked). This is the fork between
  "full symmetric target" and "what Android apps actually reach for."
- **Deliverable:** a documented decision plus the Gradle module
  configuration reflecting it, ready for J.25–J.27 to build against.
- **Tests:** none — this is a decision-and-configuration session.

### Session J.25 — Android verification: message classes + JSON

- **Depends on:** J.24 merged.
- **Deliverable:** verified on an actual Android build: message classes
  (protobuf-java POJOs+builders, portable as generated); JSON
  (de)serialization, only if J.24 picked the full runtime.
- **Tests:**
  - Integration: a real Android build depending on the generated message
    classes, exercising construction/serialization on-device.

### Session J.26 — Android verification: gRPC client

- **Depends on:** J.24 merged; J.3 (gRPC stubs) merged.
- **Deliverable:** verified on an actual Android build: gRPC client
  (`io.grpc:grpc-android` + `grpc-okhttp`, additive to J.3's stub
  generation, not a replacement).
- **Tests:**
  - Integration: a real Android build making a live gRPC call against a
    generated server.

### Session J.27 — Android verification: ZMQ client + track acceptance gate

- **Depends on:** J.24 merged; J.18 (ZMQ core) merged.
- **Deliverable:** verified on an actual Android build: ZMQ client
  (JeroMQ, unverified specifically on Android vs. desktop/server JVM
  until this session).
- **Out of scope:** DB/CRUDL, REST/SOAP servers, gRPC service impl — not
  consumed on-device at all (a phone doesn't host these).
- **Tests:**
  - Integration: a real Android build exchanging a message over ZMQ.
- **Acceptance gate:** this is the *track's* actual "done" bar per
  `../README.md` §8 — not just "Java target builds and passes its own
  tests," but "the Android consumption path was verified for real,"
  across message classes (J.25), gRPC (J.26), and ZMQ (this session).

## Watch for

- J.1's codegen-timing decision and J.24's runtime-variant decision are
  the two forks `../README.md` §4 calls out as having "no single
  obviously-correct answer" — don't default either one silently.
- Schema-evolution/migration support for the Java DB layer is explicitly
  not scoped in J.5–J.9 — flagged there, don't assume it's implied.
- Don't extrapolate this track's Java-specific costs to Rust/Node ahead
  of time (same discipline previously applied to Python — see
  `../../README.md` §4 for the full extrapolation-rejection history).
  Python is still the next language after Java, not dropped.
- If `plans/medical_devices/schedule/thread-4-platform-infra/track-j-java-target.md`'s
  compliance-aware layer is picked up, keep this file as the source of
  truth for the session breakdown — don't let a duplicate breakdown grow
  there.
