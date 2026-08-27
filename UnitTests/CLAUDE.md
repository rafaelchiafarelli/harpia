# tests — the pytest suite for the generator itself

**Pipeline role / purpose:** Verifies the harpia generator, not generated user
code. Two kinds: (1) golden-file snapshot tests (pure Python, always run) and
(2) per-stage behavioural tests that actually compile/link/run the generated
C++ (skipped automatically when the C++ toolchain is absent; run fully in Docker).

**Entry points / how to run:**
- Docker (recommended, full toolchain): `Docker/run.sh pytest`.
- Host (no toolchain, compile/run tests skip): `python3 -m venv .venv &&
  .venv/bin/pip install pytest && .venv/bin/python -m pytest`.
- Update golden snapshots after an intentional change:
  `HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest UnitTests/test_golden.py`
  then review `git diff UnitTests/golden` (the review is the point).

**Inputs → Outputs:** all tests run the generator on `HarpiaTest/test.harpia`
(+ its `Include/`), via the harnesses, and compare/compile the result.

## Harnesses (standalone, driven in a fresh subprocess)
- `run_pipeline.py` — mirrors `main.py`'s full orchestration, then dumps the
  intermediate artifacts (tokens, messages, proto/, json/, zmq/, grpc/,
  capability/, xml/, db/, migrate/, dbio/, rest/, soap/, wsdl/, gen_tests/,
  sidecars/) into an output
  dir for snapshotting. `python3 UnitTests/run_pipeline.py <output_dir>`. **rmtrees
  `<output_dir>/build` on every run.** Also loads a `ComplianceContext` (via
  `Compliance.context.load_compliance_context`, honoring
  `HARPIA_COMPLIANCE_CONFIG` same as `main.py`) and threads it into every
  stage constructor, recording a per-stage `instance.compliance is
  compliance` check into `compliance_smoke.txt` -- `test_compliance.py`'s
  integration test reads this back. Also resolves a `CryptoBackend` (F5,
  `Crypto.backend.get_backend`, honoring `HARPIA_CRYPTO_BACKEND` same as
  `main.py`) and writes it to `<build_dir>/build_metadata/crypto_backend.json`
  via `write_build_metadata` -- not collected into any snapshotted
  subdirectory, so it can't drift the golden tests. Also copies the F6
  `Doxyfile` (`Util.util.copyDoxygenFiles`) and writes the assembled
  mainpage (`Doxygen.mainpage.write_mainpage`) into `<build_dir>`, same as
  `main.py`.
- `run_frontend.py` — runs only the front-end (pre_lex → lexer → MessageCreator)
  on one file and prints `RESULT PRELEX/LEX/MSG <ErrorType>` or `RESULT OK`.
  `python3 UnitTests/run_frontend.py <file> <dest>`.
- `run_phi_check.py` — front-end + `FileCreator` (Stages 0-6) on one file;
  prints one `PHI_CHECK_RESULT <json>` line: `{"error": ..., "fields":
  [{"message","field","is_phi"}, ...], "messages":
  [{"name","is_critical","is_enum"}, ...], "proto": "<concatenated .proto
  text>"}`. Used by `test_phi_modifier.py` (Foundation F2, `variable.is_phi`)
  and `test_critical_modifier.py` (sensitive-data roadmap Phase 1a,
  `Message.is_critical`) to inspect the sensitive-data modifier flags and
  confirm the emitted `.proto` is unaffected by either.
  Unlike `run_frontend.py`, does NOT `chdir` into the fixture's folder --
  `FileCreator.Process()` needs repo-root-relative `./Assets/...` to
  resolve its service-proto template, so it stays at the repo root and
  passes `pre_lex` an absolute file path instead (accepted as-is by
  `isFileInFolders`). `python3 UnitTests/run_phi_check.py <file> <dest>`.
- All three run in a **fresh process** because `LexicalAnalyzer` accumulates
  tokens in class-level state — a clean interpreter per run is required.
  Tests invoke them via `subprocess`.

## Test files
- `test_golden.py` — snapshots every intermediate artifact vs `UnitTests/golden/`.
  Python only. Honors `HARPIA_UPDATE_GOLDEN=1` to rewrite snapshots.
- `test_frontend.py` — front-end error paths return the right `Error` type.
  Python only.
- `test_compliance.py` — Foundation F1's `Compliance/context.py`: missing
  config / omitted field falls back to the strictest profile per-field; a
  fully-specified config parses; an unknown/invalid enum value or a
  malformed `jurisdiction` list is a hard `ComplianceConfigError`, never
  silently defaulted; `HARPIA_COMPLIANCE_CONFIG` env override. Integration:
  runs the real pipeline (`run_pipeline.py`, with a compliance config
  present) and reads back `compliance_smoke.txt` (a per-stage marker
  `run_pipeline.py` emits recording `instance.compliance is <the loaded
  ComplianceContext>` for every stage constructed) to confirm the exact
  object reached every one, not just a default. Pure Python.
- `test_phi_modifier.py` — Foundation F2's `phi` field modifier: parses
  with/without `phi`, alone and combined with every other modifier
  (`optional`/`required`/`unique`/`repeteable`, modifier order, a composed-
  type field), confirming `variable.is_phi` via `run_phi_check.py`.
  Integration: the emitted `.proto` for a `phi` field contains no trace of
  the modifier itself and is line-for-line identical to the same field
  without `phi` (flag only -- no encryption/redaction/audit logic lands
  with this token). Pure Python.
- `test_critical_modifier.py` — sensitive-data roadmap Phase 1a's `critical`
  message-type modifier: parses with/without `critical`, composed with each
  transport kind (`event`/`stream`/`push`/`pull`), order-independent, and
  together with a `phi` field on one message (design-rules Rule 0 — the two
  axes are independent). Confirms `Message.is_critical` via `run_phi_check.py`.
  Integration: the emitted `.proto` for a `critical` message contains no trace
  of the modifier and is line-for-line identical to the same message without
  it (flag only — the delivery-guarantee machinery is Phase 3). Pure Python.
- `test_delivery_runtime.py` — sensitive-data roadmap Phase 3a's
  `Compliance/runtime/harpia_delivery.h` (hand-written C++, like
  `harpia_audit_sink.h` — compiles/runs small standalone programs against the
  header, `-Werror`, no generated project). `Envelope` origin-CRC + `crc_ok()`
  catches a mutated payload; `check_on_arrival` → Ok/CrcMismatch/SeqGap/
  SeqRegressed; `BoundedQueue` FIFO within capacity, overflow rotates the
  oldest with an observable `PushOutcome` + `rotations()` count +
  `last_rotated_seq()` + a `"queue_rotated"` `AuditSink` record (via a
  counting test sink — proves it's never a silent drop); `Mailbox` latest-
  value-only, `put()` overwrites with `PutOutcome` + `"mailbox_overwritten"`
  record; `peek()` is a non-destructive, order-stable look at the queue
  front; a Phase 3c rehearsal (stall overruns the queue, drain replays the
  survivors in order, every loss audited). (g++)
- `test_critical_delivery_roundtrip.py` — Track D / Session D.4
  (`Initiatives/medical_devices/epics/thread-6-critical-and-phi/`): the
  `critical` send/receive headline integration test. protoc+g+++pkg-config+
  libzmq+cppzmq-gated. Drives the generated `alarm_event` transport over a
  real `tcp://` socket: (1) publish-while-stalled holds N in the
  `BoundedQueue` (`pending()` grows, socket untouched), `flush()` after the
  subscriber joins replays all N in seq order; (2) `queue_capacity=4` +
  a 10-message burst through a `CountingSink` rotates the oldest exactly 6
  times (`"queue_rotated"` audited, `pending()` stays 4), `flush()` then
  delivers the newest 4 in order; (3) `courier_sender` (non-`critical`) has
  no `flush()`/`pending()`/`queue()` (detection traits) and `send()` stays
  synchronous `bool`. Case 1 has one timing dependency — a 300 ms PUB/SUB
  subscription settle (`_SETTLE_MS`). Pins `HASH`.
- `test_zmq_critical_delivery.py` — sensitive-data roadmap Phase 3b: pure
  Python / structural. Runs the real pipeline (`run_pipeline.py`, no C++
  toolchain) and asserts `alarm_event` (`critical event`) gets a
  publisher that `#include`s `delivery/harpia_delivery.h`, holds a
  `BoundedQueue queue_` + `next_seq_`, whose `publish()` returns
  `std::optional<PushOutcome>` and enqueues an `Envelope::stamp(...)`
  instead of firing the socket, with a separate `flush()` doing the
  `peek()`/`pop()` drain; the subscriber half is untouched;
  `courier`/`users` (non-critical) headers contain no `delivery::`/
  `BoundedQueue` at all; `harpia_delivery.h` + `harpia_audit_sink.h` are
  copied verbatim into `generated/cpp/delivery/`; and driving `ZmqAdapter`
  directly with a lone non-critical message creates no `delivery/` dir.
- `test_audit_sink.py` — Foundation F3's `Compliance/runtime/harpia_audit_sink.h`
  (hand-written C++, not Python -- unlike F1, this interface is injected
  into *generated* code by later tracks). Compiles/runs small standalone
  programs directly against the header (no generated project needed):
  `NoOpAuditSink.record()` has no side effect and doesn't crash, works
  through an `AuditSink&` base-class reference, `default_audit_sink()`
  returns the same shared instance every call, and a dummy generated-shaped
  class can take `AuditSink&` (defaulted or explicit) in its constructor
  and call `record()` without the sensitive value ever reaching it. (g++)
- `test_crypto_backend.py` — Foundation F5's `Crypto/backend.py`
  `CryptoBackend` selection point: explicit name / alias resolution /
  unknown-name hard error (same shape as `Database.backends.get_backend`);
  `risk_class == CLASS_C` or `topology == CLOUD_CONNECTED` defaults to the
  FIPS backend, an explicit name overrides that default; `get_backend()`
  returns the identical singleton across calls (the acceptance-gate proof
  that Track O and Track C, once built, would provably share one crypto
  module); `write_build_metadata()` produces a valid
  `build_metadata/crypto_backend.json` sidecar and is write-if-different
  (stable mtime when unchanged). Pure Python.
- `test_key_provider.py` — Track O / Session O.1
  (`Initiatives/medical_devices/epics/thread-1-data-and-keys/histories/key-management/`):
  the `KeyProvider` interface + envelope-encryption shape,
  `Crypto/runtime/harpia_key_provider.h` (hand-written C++, same
  compile-and-run pattern as `test_audit_sink.py`/`test_delivery_runtime.py`,
  `-Werror`). `Dek` wrap/unwrap round trip; `seal`/`open` survives a DEK
  wrap/unwrap in between; `WrappedDek` records the active KEK version;
  `rotate()` bumps the version, old DEKs still unwrap, no existing
  `WrappedDek` is mutated (O(keys), not O(data)); an unknown or
  `forget_kek_version()`-dropped KEK version makes `unwrap_dek` return
  `nullopt` (Rule 5 — and the O.3 crypto-shred path, early); polymorphic
  use through `KeyProvider&`. (g++)
- `test_local_key_provider.py` — Track O / Session O.2: the default no-KMS
  `LocalKeyProvider` (`Crypto/runtime/harpia_key_provider_local.h`).
  Satisfies O.1's `KeyProvider` contract unmodified; KEK material persists
  across instances pointed at the same `storage_path` (rotation included) —
  the "local storage" difference from O.1's in-memory provider; the ctor
  throws `LocalKeyProviderRefused` when `phi_at_scale && !acknowledged` and
  proceeds with the acknowledgment; the gate doesn't bite when not at
  scale; `local_key_provider_acknowledged()` reads
  `HARPIA_ACK_LOCAL_KEY_PROVIDER` (`1`/`true`/`yes`, any case). (g++)
- `test_doxygen_mainpage.py` — Foundation F6's `Doxygen/mainpage.py`:
  extracts only the requested `USAGE.md` section numbers (not their
  neighbors), in the requested order, stopping at the next `## ` heading
  rather than swallowing it; raises on a missing section number; against
  the real repo `USAGE.md`, the default `(4, 6, 11)` sections extract
  cleanly; `write_mainpage()` is write-if-different. Pure Python.
- `test_doxygen_docs.py` — Foundation F6's `Assets/Doxyfile` + CMake
  `doxygen` target. `Doxyfile`/`USAGE_EXCERPT.md` land in a real generated
  project (ungated). Doxygen-gated: a tiny synthetic fixture (one
  Doxygen-documented class, one not) proves `WARN_IF_UNDOCUMENTED=YES`
  actually catches the gap and stays clean on the documented one --
  deliberately NOT run against the real generated project's own headers,
  since none of them use real Doxygen comment syntax yet (that's Ground
  Rule 6's job, ongoing per-track, not F6's one-time plumbing -- see the
  module's own docstring for the full reasoning). Doxygen+cmake+protoc-
  gated: configures the real generated project and builds the `doxygen`
  target end to end, asserting real HTML output containing the mainpage
  content -- without asserting on warning count. (doxygen, cmake, protoc)
- `test_java_proto_options.py` — session J.1 (`Initiatives/multi-language-targets/thread-1-java-target`): every emitted message `.proto` carries `option java_multiple_files = true;` + `option java_package = "com.harpia.generated";`, placed before the message body; protoc still parses the emitted `.proto` cleanly. Pure Python, plus one protoc-gated syntax check.
- `_java_gradle_helpers.py` — shared harness for every Java-target gradle+JDK-gated test (not itself a test module): `generate(tmp_path, lang=...)` runs `main.py` with `HARPIA_GEN_LANG`; `build_and_classpath(java_root, extra_source)` drops smoke `.java` source into the generated Gradle project, runs `gradle build`, then resolves a runnable classpath via the `harpiaRuntimeClasspath` task `GradleAdapter` wires into every generated `build.gradle` — deliberately not hand-globbing exact jar paths out of the Gradle dependency cache (fragile: breaks on any pinned-version bump or new transitive dependency).
- `test_java_gradle_wiring.py` — sessions J.2/J.3 (`Initiatives/multi-language-targets/thread-1-java-target`): `HARPIA_GEN_LANG=java` (default `cpp`, unaffected) stands up a self-contained Gradle project under `<dest>/java/` (`GradleAdapter`, see its `CLAUDE.md`). Structural (pure Python, always run): default/`cpp` don't create `java/` at all; `java` wires `build.gradle`/`settings.gradle` (grpc plugin block included) + a copy of every message `.proto` AND `_service.proto`, plus the `errorCode`/`heartBeat` framework protos those import (NOT `capabilities_service.proto`, an unrelated capability-advertisement service) — all carrying `java_multiple_files`/`java_package`; write-if-different (stable mtime on an unchanged rerun). Integration (gradle+JDK-gated, not part of the harpia Docker image yet, two tests, via `_java_gradle_helpers`): a real `gradle build` compiles the protobuf-gradle-plugin-generated classes, then one smoke program constructs a message via its generated builder and round-trips a field (J.2), another instantiates the generated gRPC stub's `ImplBase` to prove it compiles and links against grpc-stub/grpc-protobuf (J.3).
- `test_java_db_crudl.py` — sessions J.5/J.6/J.7 (landed together): `JavaDatabase`'s reflection-based JDBC bind/extract runtime (`JdbcBind`, see its `CLAUDE.md` for why reflection over typed accessors) and generated per-message `<name>_dao` CRUDL classes. Structural (pure Python): the runtime + `sqlite-jdbc` dependency are wired in; `users` (all-scalar) gets a complete DAO; `top_users` (has a singular FK) still gets a DAO, with the FK column noted as deferred rather than silently dropped or broken. Integration (gradle+JDK-gated): J.5's bind/extract round-trips every supported kind (int/int64/float/string/enum) directly, no DAO involved; J.6 drives `users_dao` through a full create/read/update/list/remove cycle; J.7's acceptance gate writes in one `java` process and reads back in a genuinely separate one, proving the SQLite file persisted rather than just staying alive in the writer's memory.
- `test_java_xml.py` — sessions J.10/J.11 (landed together, one runtime file): `com.harpia.runtime.xml.HarpiaXml`, a single reflection-based `toXml`/`fromXml` runtime class (no per-message generation — see `JavaXmlAdapter/CLAUDE.md`). Structural (pure Python): the runtime class is wired in. Integration (gradle+JDK-gated): `shipment`+`parcel` (nested + repeated) serialize correctly; `patient_vitals.device_note` (`optional string`) is presence-gated — absent when unset, present when set (J.10); both round-trip through `toXml`→`fromXml` with values AND presence preserved, not just values (J.11) — `hasDeviceNote()` after round-tripping an unset field must stay `false`.
- `test_java_rest.py` — sessions J.12/J.13/J.14 (landed together): REST CRUD over JDK-builtin `HttpServer`, credential-gated + content-negotiated (`JavaRestAdapter`, see its `CLAUDE.md`). Structural (pure Python): the shared `HttpRestHelpers` runtime + a per-message `users_rest.java` are wired in, carrying the right credential check. Integration (gradle+JDK-gated): a real `HttpServer` on an ephemeral port, driven over real HTTP with `java.net.http.HttpClient` — no/wrong credentials get 401; a full create/read/update/list/delete cycle against `users`; a JSON create body followed by an `Accept: application/xml` read proves content negotiation actually dispatches, not just that both runtimes exist.
- `test_java_soap.py` — sessions J.15/J.16 (landed together): hand-rolled SOAP envelope access (`JavaSoapAdapter`, see its `CLAUDE.md` — not a real SOAP/WS-* stack, same as the C++ target). Structural (pure Python): the shared `SoapHelpers` runtime + a per-message `users_soap.java` are wired in. Integration (gradle+JDK-gated): a real `HttpServer` on an ephemeral port, driven over real HTTP with `java.net.http.HttpClient` posting SOAP envelopes — wrong credentials get a 401 Fault; a full set(create)/get(read)/update/delete envelope cycle against `users`; a get after delete comes back as a "not found" Fault at HTTP 200 (matching the C++ target's own status-code choice exactly, not upgraded to something "more correct").
- `test_java_zmq.py` — session J.18: ZMQ transport over JeroMQ (`JavaZmqAdapter`, see its `CLAUDE.md` — one shared reflection-based runtime class, `HarpiaZmq`, not 4 generated classes per message like C++). Structural (pure Python): the runtime + `jeromq` dependency are wired in; `courier` (push-only, HarpiaTest/test.harpia) gets only sender/receiver factories with a runtime origin id; `users` (pull+push+event) gets all four factories with the compile-time `ORIGIN_ID`. Integration (gradle+JDK-gated): a real PUSH/PULL round trip over `inproc://` confirms the `ORIGINATOR` field gets stamped with the sender's own runtime id; a real PUB/SUB round trip (with the classic "slow joiner" retried around) confirms publish/subscribe works too.
- `test_java_zmq_curve.py` — session J.19: CURVE-secured ZMQ (`HarpiaZmq.CurveKeys`, see `JavaZmqAdapter/CLAUDE.md` for the confidence caveat — API shape sourced from web research, not yet compiled/run against a real JDK). Structural (pure Python): generated `<name>_zmq` factories carry CURVE-taking overloads; the runtime exposes `CurveKeys`/`generateCurveKeyPair`/the JeroMQ `setCurve*` calls. Integration (gradle+JDK-gated, real `tcp://`, not `inproc://` — CURVE is a no-op over inproc, same discipline as the C++ target's own `test_stage13_zmq.py`): matching keys complete a real handshake and exchange a message; a client told the wrong server public key never receives anything (times out) rather than silently falling back to plaintext.
- `test_java_junit_tests.py` — session J.21: generated JUnit 5 tests (`JavaTestAdapter`, see its `CLAUDE.md` for what's a scoped subset of the C++ TestAdapter's ~8 body builders, and what's deliberately not ported). Structural (pure Python): a `<name>_Test.java` is generated per table-bearing message with all four `@Test` methods, built entirely via `Descriptor`/`FieldDescriptor` reflection (spot-checked: no typed-accessor calls like `setAddress(`). Integration (gradle+JDK-gated): a real `gradle test` run, asserting a green exit code AND that JUnit's own XML reports exist for at least 10 message classes (guards against a false pass where `useJUnitPlatform()` silently collected zero tests).
- `test_golden_java.py` — session J.23: the Java target's own golden-snapshot baseline (`UnitTests/golden_java/`, mirrors `test_golden.py`'s `UPDATE`/`_relpaths`/`_check` pattern but as one whole-`java/`-tree comparison rather than split per adapter subdirectory — the Java target's output is one coherent Gradle project, not C++'s dozen separately-rooted directories). Pure Python, always run: 101 files across every adapter built so far (message/service protos, all generated Java sources, `build.gradle`/`settings.gradle`) must match byte-for-byte, and regenerating twice into the same dir must not touch an unchanged file's mtime (write-if-different).
- `test_java_full_demo.py` — session J.23's "run demo" half: a cross-subsystem proof that generated layers actually interoperate through shared state, not just each pass in their own isolated fixture — a `users` row created through the REST API is read back through the DB DAO directly, via a separate JDBC connection to the same SQLite file. Gradle+JDK-gated only (no structural half — `test_golden_java.py` already covers the structural side for J.23). Note in the module docstring: every `gradle build` this thread's tests have run since J.2 already compiles the WHOLE `src/main/java` tree together and (since J.21) already runs the full generated JUnit suite via Gradle's `build` -> `check` -> `test` dependency chain — "the whole surface works together" has been continuously checked throughout this thread, not newly discovered here.
- `test_java_db_crudl_postgres.py` — sessions J.8/J.9: Postgres driver wiring for the Java target's DB layer. Confirms the prediction in `JavaDatabase/CLAUDE.md` — wiring is just the `org.postgresql:postgresql` dependency, zero DAO code changes, since `JavaCrudlAdapter` was already dialect-neutral through the shared `dbBackend`. Opt-in, same posture as `test_stage8_pg.py`: skipped unless `HARPIA_PG_DSN` (parsed into a JDBC URL) points at a reachable server AND gradle/JDK are on PATH.
- `test_java_json_pass_through.py` — session J.4: `JavaJsonAdapter` ships a single hand-written `com.harpia.runtime.json.HarpiaJson` runtime class (NOT per-message generation — see its `CLAUDE.md` for why that's correct, not a shortcut). Structural (pure Python): the runtime class is wired into `<dest>/java/src/main/java/com/harpia/runtime/json/`; `build.gradle` depends on `protobuf-java-util`. Integration (gradle+JDK-gated): a real JSON round trip through `patient_vitals`'s generated builder, confirming protobuf's canonical camelCase field mapping (`patient_id` -> `"patientId"`, never `"patient_id"`) — the literal J.4 test bar.
- `test_stage7.py` — protoc emits/compiles `.pb.{h,cc}`. (protoc, g++)
- `test_stage8_db.py` — SQL schema, CRUDL round-trip, FK, repeated-FK link table,
  map<K,V>, repeated scalar, migration, DB↔JSON/XML. (cc + g++, some protoc)
- `test_stage9.py` — JSON adapters compile + round-trip. (protoc, g++)
- `test_stage10_xml.py` — XML adapters compile, to/from_xml round-trip, XSD.
- `test_stage11_soap.py` — SOAP-over-HTTP endpoint (credential gate).
- `test_stage12_rest.py` — REST HTTP CRUD, credential-gated.
- `test_stage13.py` — gRPC services compile, CRUDL-backed impl, metadata auth.
- `test_fieldmap.py` — field-identity (wire-number freeze) unit tests, from the message-versioning effort: `message.FieldMap.freeze`
  driven directly (no lexer) — first-generation freeze, reorder/insert
  stability, delete-retires-number, rename-keeps-number, unresolvable-rename
  falls back (mirrors `Database/MigrationAdapter`'s conditional RENAME),
  hidden-field (`ID_`/`STATUS_`/`ERROR_`/`ORIGINATOR`) stability across an
  md5 hash change, reserved-number-reuse hard error, sidecar path shape.
  Pure Python.
- `test_fieldmap_frontend.py` — the same §3 reorder/delete properties but
  through the real front-end pipeline (`run_frontend.py`, fresh subprocess
  per generation), confirming `Message/Message.py`'s wiring actually calls
  `FieldMap.freeze`, not just the module in isolation. Pure Python.
- `test_message_versioning_wire.py` — §3's integration test: two real
  generations of one root `.harpia` file (same schema_registry sidecar),
  the second reordering fields and adding one; compiles gen1's protobuf
  class into a "writer" program and gen2's into a separate "reader",
  proving a real serialized message survives the reorder. (protoc, g++)
- `test_message_versioning_parse_boundary.py` — §4: JSON tolerates an
  unrecognized key (`ignore_unknown_fields`); an `optional`-tagged field's
  `has_<field>()` distinguishes "never set" from "explicitly set to the
  zero value" through both the protobuf binary and XML round trip (the
  latter proving the `harpia_xml.h` `has_presence()` fix specifically); a
  newer schema's added field, written by a "new" binary, parses cleanly on
  an "old" binary that never heard of it (inverse direction of
  `test_message_versioning_wire.py`). (protoc, g++)
- `test_message_versioning_capability.py` — §5's gRPC capability handshake:
  `harpia::capability::negotiate()` gets a real server's advertised
  message-type set over an in-process channel; a peer with other services
  registered but not `capabilities_service` (a genuine pre-feature legacy
  peer) resolves to the named "legacy peer" outcome, not a hang;
  `harpia::capability::Dispatcher` (shared, transport-agnostic -- tested
  once here, not per transport) routes a covered type to its handler and
  falls back (never silently) for an uncovered type or a covered type with
  no registered handler. (protoc, grpc_cpp_plugin, g++)
- `test_message_versioning_capability_http.py` — §5's REST/SOAP capability
  handshake (shared: both ride the same `crow::SimpleApp`): a real Crow
  server's `GET /capabilities` route answers `negotiate()` correctly; a real
  server with other routes but no `/capabilities` (legacy peer) and an
  unreachable host both resolve to the named legacy-peer outcome. All three
  cases pass. The two Crow-server cases used to fail here for a
  pre-existing, unrelated reason (`third_party/asio` was missing several
  headers, breaking anything that `#include`s `crow.h`) -- resolved
  2026-08-23 by re-vendoring the missing headers, see `NEXT_SESSION.md`'s
  resolved note and `HttpCapabilityAdapter/CLAUDE.md`. (protoc, g++, cc)
- `test_message_versioning_capability_zmq.py` — §5's ZMQ capability
  handshake: a real REQ/REP round trip (`capabilities_responder` +
  `negotiate()`) over `inproc://`; a real `tcp://` port with nothing
  listening resolves to the named legacy-peer outcome within the deadline,
  not a hang. No `crow.h`/asio dependency, so unaffected by the gap above --
  both tests pass. (protoc, g++, libzmq, cppzmq)
- `test_stage13_zmq.py` — ZMQ PUSH/PULL round-trip over a real socket, plus a
  CURVE round-trip over real `tcp://` (matching keys succeed, a wrong server
  public key times out -- CURVE is a no-op over `inproc`, which the other
  tests here use, so this one needs a real handshake).
- `test_stage14.py` — every generated `*_test.cpp` compiles/runs green; CTest
  wiring; `cmake -DHARPIA_BUILD_TESTS=ON` + `ctest`.
- `test_stage8_pg.py` — **opt-in** live-PostgreSQL CRUDL round-trip (generates with
  `HARPIA_DB_BACKEND=postgresql`); skipped unless `HARPIA_PG_DSN` points at a
  reachable server.
- `test_consumer_example.py` — downstream-consumption contract: builds + runs
  `HarpiaTest/app_example/consumer/` against a freshly generated project
  (`cmake -DHARPIA_GEN=<gen>`), asserting the black-box wiring still works.
  Also builds/runs it with `-DUSE_TLS=ON` and does a real TLS handshake
  (`ssl.get_server_certificate`) against the running server.
- `test_incremental_regen.py` — regeneration is write-if-different, not a
  blanket wipe (see `Util.util.write_if_different`/`prune_stale_outputs`,
  `main.py`). Runs the pipeline twice against the *same* persistent output
  dir (the only place in the suite that does): once with unchanged input,
  asserting a generated file's mtime doesn't move; once renaming a message
  between runs (root file's own text unchanged, so its hash stays stable —
  the normal `Include/`-editing workflow), asserting the old name's output
  is pruned. Uses a tiny inline two-file fixture, not the shared
  `HarpiaTest/Include` ones, so it doesn't touch the pinned `HASH` below.
- `test_atomic_write.py` — crash-safety of `write_if_different`/
  `copy_if_different`: simulates a kill between the temp-file write and the
  atomic rename (`os.replace` monkeypatched to raise) and asserts the
  destination is left exactly as it was, with no leftover temp file. Pure
  Python.
- `test_demo.py` — end-to-end: build generated project with its own CMake, run
  client→server. (cmake, protoc, grpc_cpp_plugin, g++, libzmq) Also builds and
  runs it a second time with `-DUSE_ZMQ_CURVE=ON` (over `ipc://`, which -- like
  `tcp://` -- goes through the real ZMTP handshake), confirming the ephemeral
  keypairs the configure-time keygen probe writes actually match between the
  server and client binaries from the same build.

## The pinned HASH constant — matters for the multi-root feature
`test.harpia` (and its includes) hash to an md5 the generator uses to key every
emitted filename. It is currently **`3ac5d8b36fc7dcfb70888145147ddfb7`** (bumped
2026-08-24, `Initiatives/feature-examples` Session EX.1, when `pope`/`king`/
`queenBee` were folded into `queen` — that changed `test.harpia`'s own text, see
`LexicalAnalizer/CLAUDE.md`: only the root file's text is hashed), pinned as a
top-of-file `HASH = "..."` constant in **sixteen** files, not the six this doc
used to claim — **that stale six-file list is exactly what caused EX.1 to miss
ten of them on the first pass** (`UnitTests/test_java_db_crudl.py` specifically hard
NPE'd at runtime — `Descriptors$FieldDescriptor.getContainingType()` on a null
field — because a generated Java field genuinely renamed
(`ID_c96f8fd7...` → `ID_3ac5d8b3...`) while the test still looked it up by the
old name). The full, actual list (re-derive via `grep -rl '^HASH = "<hash>"'
UnitTests/*.py` before ever trusting this list again):
- `test_stage8_db.py`, `test_stage10_xml.py`, `test_stage11_soap.py`,
  `test_stage12_rest.py`, `test_stage13.py`, `test_stage13_zmq.py`,
  `test_critical_delivery_roundtrip.py`
- `test_java_db_crudl.py`, `test_java_full_demo.py`, `test_java_gradle_wiring.py`,
  `test_java_junit_tests.py`, `test_java_rest.py`, `test_java_soap.py`,
  `test_java_zmq.py`
- `test_message_versioning_capability_http.py`,
  `test_message_versioning_parse_boundary.py`
- `test_stage8_pg.py`

Plus **one file with the hash as a raw literal, not a `HASH` variable at all**:
`test_message_versioning_capability_zmq.py` hardcodes
`capability/capabilities_<hash>_zmq.h` directly inside an embedded C++ `#include`
string.

If `test.harpia` or any of its includes change, this hash changes and **every
one of the above must be bumped in lockstep** (the tests build header/filenames
from it). Only the *other* test files (not listed above) derive the hash at
runtime instead of pinning it.
(Note: the README's mention of `734126ee…` is stale prose predating even the
old `c96f8fd7…` hash.)

## Golden snapshots (UnitTests/golden/)
Committed reference output keyed by the input hash. Files: `tokens.txt`,
`messages.txt`; dirs: `proto/`, `json/`, `zmq/`, `grpc/`, `capability/`
(whole-project gRPC/HTTP/ZMQ capability advertisements, S5), `xml/`, `db/`,
`migrate/`, `dbio/`, `rest/`, `soap/`, `wsdl/`, `gen_tests/` (generated unit tests
+ CTest CMakeLists), `sidecars/` (per-message SQL schema + modifier/access/pswd
flag files, subdirs `database/ modifier/ access_modifier/ database_access/`).
Do not hand-edit — regenerate via `HARPIA_UPDATE_GOLDEN=1` and review the diff.

## Key facts / gotchas
- Behavioural tests use `pytest.mark.skipif(shutil.which(...) is None, ...)` per
  required tool, so a bare host stays green; Docker has the full toolchain.
- Docker non-TTY gotcha: `Docker/run.sh` runs as your UID so generated files stay
  yours; don't pass `-it` in non-interactive/CI contexts.
- `run_pipeline.py` rmtrees its `build/` subdir each run — never point it at a dir
  whose `build/` you want to keep.
- **Resolved 2026-08-23 (Foundation thread-0 session): the `third_party/asio`
  vendoring gap that used to fail 9 tests here** (`test_consumer_example.py`,
  `test_stage11_soap.py`, `test_stage12_rest.py`, `test_stage14.py`, and two
  Crow-dependent cases in `test_message_versioning_capability_http.py` --
  anything that `#include`s `crow.h`, which pulls in `asio.hpp`, failed to
  compile) is fixed: 5 headers were missing from the vendored tree relative
  to its pinned upstream tag, not just `asio/detail/bind_handler.hpp` as
  first thought. Re-vendored from the same tag; see `NEXT_SESSION.md`'s
  resolved note for the full file list. All 9 pass now, full suite shows no
  regressions.

## Touchpoints
- Depends on: the whole generator (all adapters + front-end), `HarpiaTest/`
  fixtures, repo `third_party/` (vendored sqlite/tinyxml2/crow/asio), the
  HTTP test client `UnitTests/harpia_test_client.h`, and `Compliance.context`
  (Foundation F1).
