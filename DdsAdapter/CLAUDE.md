# DdsAdapter — header-only DDS transport (ASTM F2761 / OpenICE-class bedside bus)

**Pipeline role:** Stage 13 (dds), parallel to `ZmqAdapter` / the gRPC path. A
*third* selectable transport, not a replacement — emitted only for messages
that declare the `dds` modifier (dds-transport epic). Runs after
`ZmqCapabilityAdapter`, before `GrpcServiceAdapter`, in both `main.py` and
`UnitTests/run_pipeline.py`.

**Entry point:** `DdsAdapter(messages=msgFactory.messages, dest=testDestination,
compliance=complianceContext, crypto_backend=cryptoBackend).Process()` →
`None`, or `Error(NOTHING_TO_REPORT)` (non-fatal) when no message declares
`dds`. `crypto_backend` (the F5 `CryptoBackend`, resolved once in
`main.py` / `run_pipeline.py`) is optional — falls back to
`Crypto.backend.get_backend(compliance=…)` when omitted.

**Inputs → Outputs:** consumes `msg.name`, `msg.md5Hash`, `msg.isEnum`,
`msg.access_modifiers` (the `DDS` token), `msg.is_critical`,
`msg.variables[].is_phi` (task 4), and the F5 `CryptoBackend` +
`ComplianceContext` (task 3). Emits
`<dest>/generated/cpp/dds/<name>_<hash>_dds.h` per `dds` message, plus — when
at least one exists — the shared frame type + its CMake scaffolding
(`harpia_dds_frame.idl` + `CMakeLists.txt`), `harpia_audit_sink.h` when any
emitted `dds` message carries a `phi` field, `harpia_dds_security.h`, and a
`security/` dir (`governance.xml`, per-project `permissions.xml`,
`dds_security_selection.json`) — all into `generated/cpp/dds/`.

## Files
- `DdsAdapter.py` — `Process()` filters messages by `"DDS" in access_modifiers`
  (enums skipped), renders a header per message, then copies the frame
  scaffolding once (and `harpia_audit_sink.h` once when any `dds` message has
  a `phi` field), then `_write_security()` (task 3). `_render()` picks the
  QoS profile from `msg.is_critical`, computes the `phi` field names
  (`_phi_fields()`), and assembles `header.h.tmpl` from `qos.tmpl` +
  `pubsub.tmpl`. `_write_security()` copies `harpia_dds_security.h` + the
  static `dds_governance.xml`, renders `permissions.xml` (its `<topic>` list
  = the schema's `dds` message names) from `templates/permissions.xml.tmpl`,
  and writes `dds_security_selection.json` (`self.crypto_backend` fields +
  `transport_hardening_required(self.compliance)`).
- `runtime/harpia_dds_security.h` — hand-written, copied verbatim next to the
  per-message headers (like `harpia_audit_sink.h`). `harpia::dds_security`:
  `SecurityFiles` (the six PKI paths + `complete()`), `SecurityRefused`,
  `scoped_security_config` (RAII: installs an inline `CYCLONEDDS_URI`
  `<Security>` block for the duration of participant construction, restores
  the prior value after — Cyclone binds the config into the domain at
  creation), `secured_participant(domain_id, files, openssl_provider)`
  (throws `SecurityRefused` on incomplete files — **never a silent plaintext
  fallback**). ddscxx 0.10.5 has no C++ `Property` QoS policy, so the
  Cyclone-native config-XML route is the only one; plugin sonames are the
  builtins task 2a's `-DENABLE_SECURITY=ON` build installs
  (`libdds_security_{auth,ac,crypto}.so`).
- `runtime/dds_governance.xml` — static, copied verbatim into
  `security/governance.xml`. Fail-safe posture (master plan §0a):
  `allow_unauthenticated_participants=false`, join/read/write access control
  on, SIGN on discovery/liveliness/RTPS/metadata, ENCRYPT on payload. A
  deployment narrows the domain/topic rules and S/MIME-signs it.
- `templates/permissions.xml.tmpl` — rendered into `security/permissions.xml`.
  One grant, publish + subscribe allowed on exactly this schema's `dds`
  topics, `<default>DENY</default>`. `{not_before}` / `{not_after}` are a
  fixed 100-year window (deterministic golden); `%HARPIA_SUBJECT_NAME%` is a
  sentinel the provisioning step replaces with the identity cert's real
  RFC2253 subject before signing.
- `templates/header.h.tmpl` — outer header (guard, `dds/dds.hpp` + frame +
  `.pb.h` includes, `{audit_include}` slot — `\n#include "harpia_audit_sink.h"`
  only when the message has a `phi` field, `namespace harpia::dds_transport`,
  `{qos_block}` + `{body}` slots).
- `templates/qos.tmpl` — the two QoS functions `{name}_writer_qos(qos)` /
  `{name}_reader_qos(qos)`; `{writer_policies}`/`{reader_policies}` are the
  `qos << ...` lines, filled per profile by `DdsAdapter.py`'s
  `_CRITICAL_*` / `_LATEST_*` constants.
- `templates/pubsub.tmpl` — the `{name}_publisher` (DomainParticipant + Topic
  + Publisher + DataWriter; `publish(const Msg&)` serializes to protobuf and
  writes a `harpia_dds::Frame`) and `{name}_subscriber` (…+ DataReader;
  `receive(Msg*)` does `select().max_samples(1).take()`, unwraps, parses).
  The publisher carries four `{audit_*}` slots (ctor param, ctor init,
  member, the per-`publish()` `record()` call), all `""` for a message with
  no `phi` field — so a non-`phi` `dds` transport is byte-identical to the
  pre-task-4 output, same slot discipline as `CrudlAdapter`'s
  `_CRYPTO_CTOR_*` / `_audit()`.
- `runtime/harpia_dds_frame.idl` — the one opaque topic type every generated
  DDS transport uses: `@key string message_type; sequence<octet> payload`.
  Payload is serialized protobuf — the *same* wire bytes ZMQ / gRPC move
  (typed per-message DDS topics are future scope). Path constant in
  `Compliance/dds_common.py` (mirrors `delivery_common.py`).
- `runtime/CMakeLists.txt` — copied next to the generated headers. A
  consumer does `add_subdirectory(generated/cpp/dds)` +
  `target_link_libraries(<t> PRIVATE harpia_dds_transport)`. Runs
  `idlcxx_generate` on the frame IDL and **compiles the output in that
  subdir's scope into a STATIC `harpia_dds_transport`** — `idlcxx_generate`'s
  own target is an INTERFACE lib carrying the raw generated `.hpp`/`.cpp` as
  INTERFACE sources, which only resolve in the directory that ran it, so a
  cross-`add_subdirectory` consumer that just linked it would fail with
  "cannot find source file harpia_dds_frame.hpp".

## Key facts / gotchas
- **QoS mapping (design-rules §4, a schema-level choice never inferred at
  runtime):** `critical` → §4a ordered/complete: `Reliability::Reliable` +
  `History::KeepAll` + `ResourceLimits(QUEUE_DEPTH=128, …)` — the same
  "overflow is a resource-limit hit, not an unbounded buffer" bound as the
  ZMQ path's `BoundedQueue` (`QUEUE_DEPTH` mirrors ZmqAdapter's default
  `queue_capacity`). Non-`critical` → §4b latest-value-only:
  `Reliability::BestEffort` + `History::KeepLast(1)`. The reader QoS mirrors
  the writer so a RELIABLE writer actually matches its reader.
- **DURABILITY is left VOLATILE** in both profiles. `TRANSIENT_LOCAL`
  late-joiner catch-up is a per-use-case open question (task 2b note), not
  defaulted on — a `durability` knob is future scope.
- **Flag-only elsewhere:** `dds` never touches the `.proto` / DB / JSON / …
  output. Adding it to `alarm_event` moved only `messages.txt` / `tokens.txt`
  content + the new `dds/` files in the golden.
- **`phi`-over-DDS audit (task 4):** a `dds` message with ≥1 `phi` field
  (Foundation F2) gets a publisher holding an
  `::harpia::compliance::AuditSink&` (trailing ctor param, defaulted to
  `default_audit_sink()`), and every `publish()` records exactly one
  value-free entry — operation `"phi_publish"`, subject = the DDS topic name
  (`msg.name`), detail = the comma-joined `phi` field **names** (never a
  value, design-rules Rule 5). Same call pattern the db-encryption epic uses
  for the DB path (`phi_create` / `phi_read` / …) — the transport changes,
  the audit obligation does not. Scoped to the publish side only; the
  `{name}_subscriber` is untouched (a `phi_receive` audit was considered and
  left out — not in task 4's contract). `record()` fires **after**
  `writer_.write(frame)`. A message with no `phi` field emits no `AuditSink`
  reference at all.
- **DDS-Security (task 3):** emitted whenever the schema has any `dds`
  message — additive, no pub/sub signature change (a consumer just builds
  its participant via `harpia::dds_security::secured_participant(0, files)`
  and passes it in). *Which* crypto module the OpenSSL-backed builtin
  plugins use comes from the F5 `CryptoBackend` seam — extended for this
  task with `CryptoBackend.transport_security()` (the descriptor) and the
  module-level `transport_hardening_required(compliance)` predicate
  (`risk_class == CLASS_C` or `topology == CLOUD_CONNECTED`; the same rule
  `get_backend()` keys the FIPS default off, so DDS-Security and the
  transport-authn epic's future mTLS can't diverge on when hardening is
  mandatory). `dds_security_selection.json` records both. *Whether* a
  deployment must use it is a compliance decision (that JSON's
  `hardening_required`) — this adapter always ships the mechanism; it does
  not compile it in conditionally. The demo/test provisions a throwaway PKI
  and S/MIME-signs the governance/permissions via
  `Assets/cmake/dds_security_provision.sh` (the DDS-Security analogue of
  `Assets/cmake/curve_keygen_probe.cpp`).
- **Built in the Docker image, not inline:** the DDS headers compile against
  the Cyclone DDS + `ddscxx` the image installs to `/usr/local` from
  `third_party/cyclonedds{,-cxx}/` (task 2a, `-DENABLE_SECURITY=ON
  -DENABLE_SSL=ON`). `run_pipeline.py` does Python generation only — a
  build-verified check needs protoc + that install (`test_dds_demo.py` /
  `test_dds_phi_audit.py` / `test_dds_security.py` protoc the demo messages
  themselves, then build).

## Touchpoints
- Called by: `main.py` (step 13, dds path), `UnitTests/run_pipeline.py`
  (+ `_collect_dds`, snapshotted under `UnitTests/golden/dds/`).
- Depends on: `Util.util.loadTemplate` / `write_if_different` /
  `copy_if_different`, `Logger.logger`, `Errors.Error`,
  `Compliance.dds_common`, `Compliance.audit_common` (task 4 — the
  `harpia_audit_sink.h` path constant), `Crypto.backend`
  (`get_backend` + `transport_hardening_required`, task 3 — the F5 seam).
  Runtime depends on Cyclone `ddscxx` + protobuf; a `phi`-bearing transport
  also on `harpia_audit_sink.h` (Foundation F3); a secured participant on the
  Cyclone builtin DDS-Security plugins + OpenSSL.
- Tested by: `UnitTests/test_dds_security.py` (task 3 — structural: the
  runtime helper is shipped verbatim + is fail-safe, governance is the
  strict verbatim doc, permissions carries exactly this schema's topics with
  a default-DENY, `dds_security_selection.json` records the F5 choice and
  flips with compliance/backend, no `security/` without a `dds` message, the
  provisioning script is present + executable; + a
  cmake/g++/protoc/openssl/CycloneDDS-gated fork demo where a plain
  unauthenticated peer receives nothing while a secured peer receives the
  stream), `UnitTests/test_dds_phi_audit.py` (task 4 — structural: the
  publisher takes a defaulted `AuditSink&`, `publish()` records one
  value-free `phi_publish` entry, the subscriber is untouched, header copied,
  a no-`phi` `dds` message is byte-identical; + a cmake/g++/protoc/
  CycloneDDS-gated build that publishes N times and asserts N value-free
  `record()` calls — the `test_stage8_db.py::test_a3_*` shape for DDS),
  `UnitTests/test_dds_qos_mapping.py` (structural — profile per
  message, scaffolding copied, DURABILITY untouched),
  `UnitTests/test_dds_demo.py` (build + run: critical survives a transient
  receiver gap, non-critical collapses to the newest),
  `UnitTests/test_golden.py::test_dds_adapters`.
