# DdsAdapter — header-only DDS transport (ASTM F2761 / OpenICE-class bedside bus)

**Pipeline role:** Stage 13 (dds), parallel to `ZmqAdapter` / the gRPC path. A
*third* selectable transport, not a replacement — emitted only for messages
that declare the `dds` modifier (dds-transport epic). Runs after
`ZmqCapabilityAdapter`, before `GrpcServiceAdapter`, in both `main.py` and
`UnitTests/run_pipeline.py`.

**Entry point:** `DdsAdapter(messages=msgFactory.messages, dest=testDestination,
compliance=complianceContext).Process()` → `None`, or
`Error(NOTHING_TO_REPORT)` (non-fatal) when no message declares `dds`.

**Inputs → Outputs:** consumes `msg.name`, `msg.md5Hash`, `msg.isEnum`,
`msg.access_modifiers` (the `DDS` token), `msg.is_critical`, and
`msg.variables[].is_phi` (task 4). Emits
`<dest>/generated/cpp/dds/<name>_<hash>_dds.h` per `dds` message, plus — when
at least one exists — the shared frame type + its CMake scaffolding
(`harpia_dds_frame.idl` + `CMakeLists.txt`) copied into the same directory,
plus `harpia_audit_sink.h` when any emitted `dds` message carries a `phi`
field.

## Files
- `DdsAdapter.py` — `Process()` filters messages by `"DDS" in access_modifiers`
  (enums skipped), renders a header per message, then copies the frame
  scaffolding once (and `harpia_audit_sink.h` once when any `dds` message has
  a `phi` field). `_render()` picks the QoS profile from `msg.is_critical`,
  computes the `phi` field names (`_phi_fields()`), and assembles
  `header.h.tmpl` from `qos.tmpl` + `pubsub.tmpl`.
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
- **Built in the Docker image, not inline:** the DDS headers compile against
  the Cyclone DDS + `ddscxx` the image installs to `/usr/local` from
  `third_party/cyclonedds{,-cxx}/` (task 2a). `run_pipeline.py` does Python
  generation only — a build-verified check needs protoc + that install
  (`test_dds_demo.py` protoc's the two demo messages itself, then builds).
- **Out of scope (later tasks):** DDS-Security wiring via the F5
  `CryptoBackend` seam (task 3).

## Touchpoints
- Called by: `main.py` (step 13, dds path), `UnitTests/run_pipeline.py`
  (+ `_collect_dds`, snapshotted under `UnitTests/golden/dds/`).
- Depends on: `Util.util.loadTemplate` / `write_if_different` /
  `copy_if_different`, `Logger.logger`, `Errors.Error`,
  `Compliance.dds_common`, `Compliance.audit_common` (task 4 — the
  `harpia_audit_sink.h` path constant). Runtime depends on Cyclone `ddscxx`
  + protobuf; a `phi`-bearing transport also on `harpia_audit_sink.h`
  (Foundation F3).
- Tested by: `UnitTests/test_dds_phi_audit.py` (task 4 — structural: the
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
