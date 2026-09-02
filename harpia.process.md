# Harpia pipeline

Harpia turns one `.harpia` definition file into a self-contained, compilable
C++ project: protobuf messages, a SQL persistence layer, JSON / XML / YAML
serialization, REST / SOAP / gRPC / ZeroMQ / DDS transports, in-process event
channels, schema migration, generated tests, and — when a compliance profile
asks for it — field-level PHI encryption, delivery guarantees for critical
messages, mTLS + RBAC + bearer sessions, and a CycloneDX SBOM.

This file is the **stage-by-stage spec** of what the generator does. For the
consumer's guide ("I have a `.harpia` file, how do I use the output") see
`USAGE.md`.

---

## Inputs

- **one root `.harpia` file** + an optional `Include/` folder of modules it
  `import`s.
- **`project.harpia.yaml`** (optional) — the project-wide compliance profile.
  Resolved by `Compliance/context.py` into a `ComplianceContext`; missing file
  or omitted field falls back **per-field** to the strictest value (fail-safe).
  Fields:
  - `risk_class` — `class_a` / `class_b` / `class_c` (IEC 62304; strictest `class_c`)
  - `topology` — `standalone` / `networked` / `cloud_connected` (strictest `cloud_connected`)
  - `phi_handling` — `none` / `opt_in` / `required`
  - `jurisdiction` — free-form list of strings (feeds the compliance report only)
  - `project` — a name string (default `"default"`), the owner key for
    public/private DB segregation
  An unknown enum value or a malformed `jurisdiction` is a hard error, never a
  silent default. `risk_class == class_c` **or** `topology == cloud_connected`
  makes **`transport_hardening_required(context)`** true — the single predicate
  that turns on mTLS, RBAC, session tokens, the ZMQ ZAP allowlist and the FIPS
  crypto backend.

---

## Stage −1 — profile + crypto backend

- Load the `ComplianceContext` (above) and thread it into **every** stage
  constructor as `compliance=`. Most stages only store it; the ones that branch
  on it are called out below.
- Pick the `CryptoBackend` (`Crypto/backend.py`, F5 seam): a standard backend by
  default, the FIPS backend when hardening is required or named explicitly.
  Written as `build_metadata/crypto_backend.json`. `transport_security()` /
  `transport_hardening_required()` are read by the transport stages.
- Load the F6 Doxygen config (`Assets/Doxyfile`) and assemble the mainpage.

## Stage 0 — pre-process (`pre_lex`)

- reject non-UTF-8 bytes; check balanced parens / brackets / comments.
- resolve `import "x.harpia";` against the include folders (every import must
  end with `;` and resolve to a file present in an include folder).
- create the output tree; compute the **md5 hash of the root file's text** —
  this hash qualifies every generated filename and the hidden-field names, so
  two same-named messages from different roots never collide.

## Stage 1 — tokenize + build messages (`LexicalAnalyzer`, `MessageCreator`)

- line-by-line tokenization; strip `//` and `/* */` comments by removing their
  tokens (comment characters — brackets, quotes — inside a comment never raise).
- validate field wire numbers: present, numeric, `>= 1`, never reused.
- carve each `message` / `enum` into its own unit:
  - a message with a **trailing table name** (`… message Foo { … } foo_table;`)
    is persisted; without one it is serialize-only.
  - sub-messages (declared inside another message) may themselves own a table;
    an un-named sub-message with a table gets a hash for a name. Sub-messages
    carry **no** transport modifiers.
  - names `status` / `version` / `error` are rewritten to `h_<name>`.
  - a message referencing itself, or two messages with the same name, is an
    error.
- classify each message's **transport modifiers** (`stream` / `pull` / `push` /
  `event` / `event[cached]` / `event[not-cached]` / `dds`) and **type
  modifiers** (`critical`). These are AST flags only — a message with any of
  them emits **byte-identical `.proto`** to the same message without them.
- build a processing order from cross-message references; check every composed
  field's type name resolves.

## Stage 2 — front-end flags (`FileCreator`)

Per message / field, emit the sidecar flags later stages read:

- **access / table** — `public` / `private` visibility, table name + properties.
- **field modifiers** — `optional`, `required`, `unique`, `repeteable`
  (bounded via `pagination[N]` or unbounded → `vector`/`list`), `pagination[N]`,
  `renamed_from[old]`.
- **`phi`** (Foundation F2) — a per-field confidentiality tag. Composes with
  every other field modifier; a message may mix `phi` and non-`phi` fields.
  Flag only in the front end — the `.proto` is unaffected; the DB / serialize /
  DDS / FHIR stages act on it.
- **field-identity map** (`Message/FieldMap.py`) — freezes each field's wire
  number across regenerations (reorder-stable, delete-retires-a-number,
  rename-keeps-its-number), written to a `schema_registry` sidecar so a later
  version stays wire-compatible.

## Stage 3–4 — flag consistency

- `optional` + `required` on one field is an error; `unique` may combine with
  either.
- an unbounded `repeteable` with no table becomes an in-memory `vector`/`list`.

## Stage 5 — access rights (`FileCreator`)

- derive a per-message credential (user = message name, pswd = a hash bound to
  the tokenization result) used by the **flat** REST / SOAP / gRPC access gate.
- when `transport_hardening_required(context)` the flat gate is replaced at
  generation time by the RBAC gate (Stage 12/13, below) — the credential is
  still emitted but unused.

## Stage 6 — clean `.proto`

- emit every message + enum as protobuf (`proto3`), split across files as
  needed. Service protos (`<name>_service.proto`) for the gRPC surface, plus the
  framework protos (`errorCode`, `heartBeat`).
- `phi` / `critical` / `dds` / transport modifiers leave **no trace** here.

## Stage 7 — `protoc`

- compile every `.proto` to `.pb.{h,cc}` (message classes) and, for service
  protos, the gRPC stubs.

## Stage 8 — persistence (`Database/`)

Everything derives from one shared schema model (`Database/model.py`), so
schema, DAO SQL, migration and WSDL never drift.

- **SQL schema** (`SqlAdapter`) → `database/<name>_<hash>_table.sql`:
  `CREATE TABLE` per persisted message plus a child table per `map<K,V>`
  (`<table>__<field>`, owner+key+value), per repeated scalar (owner+ordinal+
  value), per repeated composed→table message (link table storing the child
  PK), and per repeated composed→table-less message (one column per the
  target's flattened fields). `ID_*` → INTEGER PRIMARY KEY; `required` → NOT
  NULL; `unique` → UNIQUE.
- **CRUDL DAO** (`CrudlAdapter`) → `generated/cpp/db/<name>_<hash>_crudl.h`,
  `harpia::db::<name>_dao` over SOCI: `create` / `read` / `update` / `remove` /
  `list` (+ a paginated `list(out, offset, limit)` overload, default limit from
  the field carrying `pagination[N]`) + `create_table` / `drop_table`.
  Singular FK columns persist/load the child via its own DAO; flattened
  table-less embeds become prefixed columns (`journey.path.start.city` →
  `path_start_city`); maps / repeated fields cascade through their child tables.
  - **`phi` fields (db-encryption epic)** — the DAO gains a
    `::harpia::crypto::KeyProvider& kp_` and a
    `::harpia::compliance::AuditSink& audit_` (both defaulted ctor params, so a
    non-`phi` DAO is byte-identical). `create`/`update` wrap the value in
    `encrypt_field(kp_, …)` (`enc:v1:` + hex frame over the envelope from
    `harpia_key_provider.h`); `read`/`list` run `decrypt_field[_ll|_int|_double]`.
    Exactly one value-free `audit_.record("phi_<op>", "<table>", "<phi cols>")`
    per op. Runtimes copied into `generated/cpp/crypto/`:
    `harpia_encrypted_column.h`, `harpia_key_provider{,_local,_kms}.h`,
    `harpia_audit_sink.h`.
  - **`event` messages (events-callbacks epic)** — the DAO `#include`s
    `events/<name>_<hash>_events.h` and calls `<name>_channel().publish(msg)` at
    the end of a successful `create()` and `update()` only (never read/list/
    remove); a message that is `event` **and** `phi` also records one
    `phi_event_onchange`.
- **public/private registry** (`DbRegistryAdapter`) → one project-wide
  `generated/cpp/db/harpia_db_registry.h`: every table with its visibility and
  `owner_project`, plus `db_access_check(requesting_project, table)` →
  `ALLOWED` / `DENIED_PRIVATE_CROSS_PROJECT` / `DENIED_UNKNOWN_TABLE`. A second
  generated project `#include`s this to ask "am I allowed at their table".
- **migration** (`MigrationAdapter`) → `generated/cpp/migrate/<name>_<hash>_migrate.h`,
  `migrate_<name>(db, data_transform = {})`: ensures tables exist, RENAMEs a
  column carrying `renamed_from[old]`, `ADD COLUMN` for anything an older
  version lacks, runs the caller's optional `data_transform` hook (after ADD,
  before DROP — so a new column exists to write and a retiring column still
  exists to read), DROPs columns the schema no longer declares, RETYPEs columns
  whose live type drifted. Child tables (`<table>__*`) get the same
  rename / orphan-reap / retype treatment.
- **DB ⇄ JSON/XML bulk io** (`DbIoAdapter`) → `generated/cpp/dbio/…`:
  `export_json` / `import_json` (NDJSON) and `export_xml` / `import_xml`.

## Stage 9 — JSON (`JsonAdapter`)

- `generated/cpp/json/<name>_<hash>_json.h`: `harpia::json::to_json(msg, &str)`
  / `from_json(str, &msg)` over protobuf's own JSON util (camelCase, proto3
  defaults omitted, unknown fields ignored on parse).

## Stage 10 — XML / YAML / unified serialize

- **XML** (`XmlAdapter`) → `generated/cpp/xml/`: `harpia_xml.h` (reflection
  runtime, vendored tinyxml2) + per-message wrapper. `to_xml(msg)` /
  `from_xml(str, &msg)` / `from_xml_element(node, &msg)`, plus `xsd(descriptor)`.
- **YAML** (`YamlAdapter`) → `generated/cpp/yaml/`: `harpia_yaml.h` (reflection
  runtime, no vendored lib) + wrapper. `to_yaml(msg)` / `from_yaml(str, &msg)` —
  block style, two-space indent, top-level mapping. Parses exactly the subset it
  emits, not general YAML.
- **unified façade** (`SerializeAdapter`) → `generated/cpp/serialize/`:
  - `harpia_serialize.h` — `harpia::serialize::{Format::JSON|XML|YAML,
    to_string(msg, Format), from_string(str, &msg, Format)}`. One dispatch
    point over the three engines; for a message with **no `phi`** field it is a
    straight pass-through (JSON/XML output byte-identical to the per-format
    adapters).
  - **`phi` redaction (serialization epic)** — when the message tree declares a
    `phi` field and `redaction_enabled()` (default **true**), `to_string`
    renders every `phi` value as `[REDACTED]` in all three formats through one
    reflection walk; the three engines are untouched. Redacted output is a
    lossy view, not a round-trip format.
  - `harpia_redaction.h` — `kPlaceholder`, `redaction_enabled()`,
    `set_redaction_enabled(bool)`.
  - `harpia_redaction_audit.h` — the **audited opt-out**:
    `allow_phi_print(AuditSink&, reason)` reveals real values and emits one
    `phi_unredacted_output_enabled` record; `restore_phi_redaction(AuditSink&)`
    flips back and audits it.
  - `harpia_phi_registry.h` — **generated**: a `constexpr` array of the
    schema's `(message, field)` `phi` pairs + `is_phi()` / `message_has_phi()`.

## Stage 11 — SOAP + WSDL + SDC

- **SOAP** (`SoapAdapter`) → `generated/cpp/soap/`: `<name>_<hash>_soap.h`
  registers a SOAP-over-HTTP endpoint on a `crow::SimpleApp`
  (`<Body>` holds `get` / `set` / `update` / `delete`) backed by the DAO + XML
  adapter. The transport-free parse is the hand-written seam
  `soap/harpia_soap.h` (`harpia::soap::{parse_envelope, find_operation,
  message_from_request}`) — the handler is a thin caller of it (so the fuzz
  harness exercises the real parse path).
- **WSDL** (`WsdlAdapter`) → `wsdl/<name>_<hash>.wsdl` (WSDL 1.1, document/
  literal).
- **WS-Discovery / SDC** (`SdcAdapter`) → `generated/cpp/sdc/`: a
  `<name>_<hash>_sdc.h` participant descriptor + `<name>_<hash>.wsdd.xml`
  sidecar, and `harpia_wsdiscovery.h` (C++17 responder on
  `239.255.255.250:3702`, POSIX multicast, Windows-inert) advertising the SOAP
  endpoint. Full BICEPS modelling is a design doc only (`sdc_biceps_design.md`).

## Stage 12 — REST + HTTP server bring-up (`RestAdapter`)

- `generated/cpp/rest/<name>_<hash>_rest.h`: CRUD routes on a `crow::SimpleApp`
  (`route_dynamic`), content-negotiated JSON/XML, GET-list paginated via
  `?limit=&offset=`.
- **access gate** (`Database/auth_gate.py`) — two generation-time variants,
  chosen by `transport_hardening_required`:
  - **flat**: `X-User` / `X-Pswd` headers must match the Stage 5 credential
    (401 otherwise). This is what the stage tests exercise (pinned low-risk).
  - **hardened (RBAC)**: `admin` / `main` / `guest` role check on the verified
    mTLS client-cert CN (resolved via the `HARPIA_RBAC_MAP` file — deployment
    config, not compiled in), or on the CN inside a valid `Authorization:
    Bearer` session token. Fixed matrix in `harpia_rbac.h` (admin = all,
    main = all but remove, guest = read/list/stream, heartbeat open).
    401/UNAUTHENTICATED (no identity) vs 403/PERMISSION_DENIED (wrong role);
    one value-free `rbac_denied` audit record per denial.
- **project-wide HTTP bring-up** (emitted whenever ≥1 table message exists):
  `http/http_server_bringup.h` (`harpia::http_transport::HttpServer` — every
  `register_<name>` + `register_<name>_soap` on one app), `http/harpia_http_mtls.h`
  (fail-safe `asio::ssl::context` with `verify_fail_if_no_peer_cert`),
  `http/http_server_selection.json`. When hardened it also copies
  `http/harpia_rbac.h` + `http/harpia_session.h` + `http/harpia_audit_sink.h`
  and splices a `POST <base>/session` token-issuance route.

## Stage 13 — ZeroMQ / streams / events / gRPC / capability / DDS

- **ZeroMQ** (`ZmqAdapter`) → `generated/cpp/zmq/<name>_<hash>_zmq.h` for any
  message with a transport modifier:
  - `push`/`pull` → sender/receiver; `event`/`stream` → publisher/subscriber.
    The sender stamps an **origin id** (compile-time for one-to-one/one-to-many,
    runtime-assigned for many-to-*).
  - **`critical` (critical-delivery epic)** — the sender/publisher routes
    through `harpia::delivery::BoundedQueue`: `send()`/`publish()` stamps a
    CRC-32 + monotonic-seq `Envelope` and enqueues it (returns
    `optional<PushOutcome>`), overflow rotates the oldest with a
    `queue_rotated` audit record (never a silent drop); a separate `flush()`
    drains to the wire oldest-first. Runtime copied to
    `generated/cpp/delivery/` (`harpia_delivery.h` + `harpia_audit_sink.h`).
  - **`stream` (zmq-lifecycle epic)** — an extra `<name>_stream` consumer with
    the explicit lifecycle: `setup(StreamConfig, CurveClientKeys = {})` →
    `StreamStatus`; `read([timeout_ms])` → `ReadResult` (`OK`+msg / `TIMEOUT` /
    `STOPPED` / `INVALID`), always timed, never blocking; `stop()` idempotent;
    RAII close with `ZMQ_LINGER=0`. Two synchronous time-based teardowns
    (no timer thread): a stop-deadline watchdog and dead-connection
    reclamation.
  - **CURVE** — every constructor takes a trailing defaulted curve-keys struct
    (`CurveServerKeys` on bind, `CurveClientKeys` on connect); empty = today's
    plaintext. When hardened, bind-side `CURVE_SERVER` sockets also start a
    **ZAP client-key allowlist** (`zap/harpia_zap.h` — a REP handler on
    `inproc://zeromq.zap.01` checking each client key against the
    `HARPIA_ZMQ_ALLOWLIST` file; deny-all with no file; one `zap_denied`
    record per rejection).
- **events / callbacks** (`CallbackAdapter`) → `generated/cpp/events/`: one
  `<name>_<hash>_events.h` per `event` message defining
  `harpia::events::EventChannel<T>& <name>_channel()`. `subscribe(cb)` /
  `unsubscribe(id)` / `publish(const T&)`. Dispatch is **detached-thread +
  exception-isolated** (a throwing callback neither propagates nor terminates;
  recorded as `event_callback_exception`). `event[cached]` (or bare `event`)
  replays the last value to a late subscriber; `event[not-cached]` retains
  nothing. A `phi` event channel records one `phi_event_dispatch` per publish.
  Runtime: `harpia_event_cache.h` + `harpia_audit_sink.h`.
- **gRPC service impl** (`GrpcServiceAdapter`) →
  `generated/cpp/grpc/<name>_<hash>_grpc.h`: concrete impl of the Stage 6/7
  service skeleton, RPCs backed by the DAO (`push`→create, `pullByID`→read,
  `streamSrc`→list [paginated], `heartBeat`→echo). Same flat/RBAC access gate
  as REST/SOAP. **Project-wide gRPC bring-up** (≥1 table message):
  `grpc/grpc_server_bringup.h` (`harpia::grpc_transport::GrpcServer` — every
  service on one `ServerBuilder`, mTLS or insecure `ServerCredentials` per the
  hardening flag), `grpc/harpia_grpc_mtls.h` (fail-safe: incomplete PEM paths
  under hardening → throw, never a silent downgrade),
  `grpc/grpc_server_selection.json`. When hardened, also `grpc/harpia_rbac.h` +
  `grpc/harpia_session.h` (`heartBeat` mints a `harpia-session-token` on
  `harpia-issue-session` metadata; gated RPCs accept `authorization: Bearer`).
- **capability handshake** (`{Grpc,Http,Zmq}CapabilityAdapter`) →
  `generated/cpp/capability/`: a per-project advertisement of the message-type
  set + `harpia::capability::{negotiate(), Dispatcher}` — a peer without the
  capability service resolves to a named "legacy peer" outcome, never a hang.
- **DDS** (`DdsAdapter`) → `generated/cpp/dds/<name>_<hash>_dds.h` for any `dds`
  message: per-message publisher/subscriber with the QoS mapping
  (`critical` → RELIABLE + KEEP_ALL + RESOURCE_LIMITS, else BEST_EFFORT +
  KEEP_LAST(1)). DDS-Security via the `CryptoBackend` seam: fail-safe
  `secured_participant` (`SecurityRefused`, never a silent plaintext peer),
  strict `security/governance.xml`, per-schema `security/permissions.xml`,
  `security/dds_security_selection.json`; throwaway-PKI provisioning script.
  A `phi` field over DDS emits one value-free `phi_publish` audit record per
  publish. Vendored Cyclone DDS + `ddscxx`.

## Stage 14 — generated tests (`TestAdapter`)

- `tests/<name>_test.cpp` per table message + a CTest `CMakeLists.txt`
  (`cmake -DHARPIA_BUILD_TESTS=ON` → `ctest`): simple access, DB round-trip,
  access rights, access modifiers, JSON/XML parse. Under a hardened profile the
  bodies are RBAC-aware (role×operation matrix + fail-closed 401 asserts).
- demo `client/` + `server/` apps (`Assets/`), buildable with `-DUSE_TLS=ON` /
  `-DUSE_ZMQ_CURVE=ON`.

## Stage 15 — compliance report (`ComplianceReport/`)

- `generated/ComplianceReport/`:
  - `bom.json` — a CycloneDX 1.5 SBOM (vendored versions from the checked-in
    `VENDORED.md` files, toolchain versions, and six `harpia:git_*` provenance
    properties from `Util/gitstate.py`).
  - `traceability.{json,md}` — a requirement catalog (`requirements.py`) mapped
    to the code + tests that satisfy each entry.
  - `compliance_report[.<jurisdiction>].md` — per-jurisdiction document shells
    over the same evidence.

---

## Companion runtime headers (hand-written, copied verbatim into the output)

| header | lands in | provided by | purpose |
|---|---|---|---|
| `harpia_audit_sink.h` | `compliance/`, `crypto/`, `delivery/`, `events/`, `http/`, `grpc/`, `zap/`, `serialize/` | Foundation F3 | `AuditSink::record(op, subject, detail)` — metadata only, structurally cannot carry a value (design-rules Rule 5); `NoOpAuditSink`; `default_audit_sink()` |
| `harpia_key_provider.h` / `_local.h` / `_kms.h` | `crypto/` | key-management epic | `KeyProvider` (envelope encryption, KEK rotation, per-DEK crypto-shred, zeroizing `Dek`); no-KMS `LocalKeyProvider`; KMS/HSM `KmsKeyProvider` + `MockKms` |
| `harpia_encrypted_column.h` | `crypto/` | db-encryption epic | `encrypt_field` / `decrypt_field{,_ll,_int,_double}` — `enc:v1:` hex frame over the envelope; unrecoverable → default, never a throw |
| `harpia_delivery.h` | `delivery/` | critical-delivery epic | `Envelope` (origin CRC-32 + monotonic seq), `check_on_arrival`, `BoundedQueue` (rotate-oldest + audit), `Mailbox` (latest-value + audit), `peek()` |
| `harpia_event_cache.h` | `events/` | events-callbacks epic | `EventChannel<T>` — subscribe/unsubscribe/publish, detached-thread dispatch, `CacheMode::{Cached, NotCached}` |
| `harpia_serialize.h` / `harpia_redaction.h` / `harpia_redaction_audit.h` | `serialize/` | serialization epic | unified `to_string`/`from_string` façade + `phi`→`[REDACTED]` control point + audited opt-out |
| `harpia_rbac.h` | `http/`, `grpc/` | transport-authn epic | `Role`, `Operation`, the fixed `permitted(role, op)` matrix, `RoleMap` (from `HARPIA_RBAC_MAP`), `decide(cn, op, subject, sink)` |
| `harpia_session.h` | `http/`, `grpc/` | transport-authn epic | bearer session tokens — HMAC-SHA256 (self-contained SHA-256) over CN + role + expiry + jti; `issue` / `verify` / `from_authorization`; `RevocationList` (`HARPIA_SESSION_REVOCATIONS`) |
| `harpia_http_mtls.h` / `harpia_grpc_mtls.h` | `http/` / `grpc/` | transport-authn epic | fail-safe mTLS context / credentials — incomplete PEM paths under hardening → throw |
| `harpia_zap.h` | `zap/` | transport-authn epic | CURVE ZAP client-key allowlist handler (`HARPIA_ZMQ_ALLOWLIST`), deny-all default, `zap_denied` audit |
| `harpia_dds_security.h` | `dds/security/` | dds-transport epic | fail-safe `secured_participant`, governance/permissions plumbing |
| `harpia_wsdiscovery.h` | `sdc/` | sdc-biceps epic | C++17 WS-Discovery responder advertising the SOAP endpoint |
| `harpia_soap.h` | `soap/` | static-fuzz-ci epic | transport-free SOAP envelope parse seam |
| `harpia_db_registry.h` | `db/` | db-segregation epic | project-wide table visibility + `db_access_check` (**generated**, not copied) |
| `harpia_phi_registry.h` | `serialize/` | serialization epic | the schema's `(message, field)` `phi` pairs (**generated**, not copied) |
| `harpia_xml.h` / `harpia_yaml.h` | `xml/` / `yaml/` | XML/YAML adapters | reflection serialization runtimes |
| `harpia_capability_dispatch.h` | `capability/` | message-versioning | transport-agnostic capability `Dispatcher` |

---

## The `.harpia` grammar in one place

```
import "mod.harpia";                       // from an Include/ folder

enum Name { a; b = 3; c; }                 // exactly one enumerator must be 0

[type-mod] [transport-mod...] message Name {
    [field-mod...] <type> field;           // int | string | Enum | Message |
                                           //   map<K,V> | repeteable <t>
    message Sub { ... } sub_table;         // nested; may own a table; no mods
} [table_name];                            // trailing name => persisted
```

- **transport modifiers** (message): `stream`, `pull`, `push`, `event`,
  `event[cached]`, `event[not-cached]`, `dds` — combinable; emit identical
  `.proto`.
- **type modifier** (message): `critical` — delivery guarantees; combinable
  with any transport modifier; identical `.proto`.
- **field modifiers**: `optional` / `required` (mutually exclusive), `unique`,
  `repeteable`, `pagination[N]`, `renamed_from[old]`, `phi`.
- **types**: `int`, `string`, an enum name, another message name (composed —
  embed or FK), `map<K,V>`, `repeteable <type>`.

`HarpiaTest/test.harpia` + `HarpiaTest/Include/file3.harpia` exercise every
construct and are the canonical worked example.
