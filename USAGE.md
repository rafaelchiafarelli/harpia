# Using Harpia

Harpia is a **code generator**: you write a `.harpia` definition file describing
your messages, and Harpia emits a self-contained, compilable C++ project with
persistence, serialization and transport already wired up — and, when a
compliance profile asks for it, field-level PHI encryption, delivery guarantees,
mTLS + RBAC + bearer sessions, and a CycloneDX SBOM.

Treat Harpia as a **black box**: give it a `.harpia` file, get a buildable C++
project out. You never modify the Harpia repo to use it. For *what each pipeline
stage does internally*, see `harpia.process.md`.

---

## 1. Quick start

```sh
./run_harpia.sh <input_folder> <output_folder>          # generate + build + test
./run_harpia.sh HarpiaTest /tmp/my_project              # using the bundled sample
./run_harpia.sh HarpiaTest /tmp/my_project --no-build   # generate only
```

Runs the whole pipeline inside the `harpia-build` Docker image (Docker is the
only host dependency), writes a portable C++ project into the output folder,
then builds it and runs its generated `ctest` suite. Both folders may live
anywhere; the output folder is regenerated **write-if-different** (§16) — safe to
reuse across runs, never wiped first.

---

## 2. The input folder

Exactly **one** root `.harpia` file, plus an optional `Include/` folder of
modules it imports:

```
HarpiaTest/
├── test.harpia          # the one root definition file
├── Include/
│   └── file3.harpia     # pulled in via  import "file3.harpia";
└── schema_registry/     # WRITTEN BY HARPIA on the first run -- commit it (§5.4)
```

---

## 3. The `.harpia` language

A `.harpia` file declares **enums** and **messages**. A message with a trailing
table name is persisted; the modifiers before `message` choose which surfaces
are generated.

```harpia
import "file3.harpia";

enum grower { g_a; g_b; g_c = 14; g_d; g_e = 0; }   // one enumerator must be 0

// plain (serialize-only) message: no trailing table name
message prince {
    pagination[12] int vari;                        // bounded repeated hint / list default limit
    optional int val;                               // real presence (has_val())
    required map<string,int> b;                     // map field -> child table
    repeteable int scores;                          // repeated scalar -> ordinal child table
};

// persisted message: transport modifiers + a trailing table name
stream pull push event message data {
    int i;
    prince val;                                     // composed field (embed / FK)
    grower car;                                     // enum-typed field
    repeteable int tags;
} table_data;

// nesting + 1-to-1 and 1-to-many references
stream pull push event message top_users {
    required string name;
    event message vip_users {
        string family;
    } table_vip_users;
    vip_users myUsers;                              // singular composed (FK)
    repeteable vip_users members;                   // repeated composed (1-to-many link table)
} user_table;
```

### Modifiers

| Modifier | On | Meaning |
|---|---|---|
| `stream` | message | ZMQ streaming consumer with an explicit setup/read/stop lifecycle (§10) |
| `pull` / `push` | message | ZMQ pull/push (request/one-way) transport (§10) |
| `event` / `event[cached]` / `event[not-cached]` | message | in-process publish/subscribe channel (§11); bare `event` = cached |
| `dds` | message | publish/subscribe onto an ASTM F2761 / OpenICE-class DDS bus (§14) |
| `critical` | message | delivery guarantees — bounded rotating send queue + flush (§12), DDS RELIABLE/KEEP_ALL |
| `optional` / `required` | field | presence (`has_<field>()`) / NOT NULL; mutually exclusive |
| `unique` | field | UNIQUE column |
| `repeteable` | field | repeated field (ordinal child table, or `vector`/`list` if unbounded and table-less) |
| `pagination[N]` | field | bounded-size hint; on a table message its `N` is the default GET-list page size |
| `renamed_from[old]` | field | this field replaces `old` — `migrate_<name>` renames the live column instead of drop+add |
| `phi` | field | protected health information — field-level encryption at rest, `[REDACTED]` in serialization, audit on access (§9) |

Transport/type modifiers are **AST flags only**: a `critical event dds` message
emits byte-identical `.proto` to the same message with none of them.

`HarpiaTest/test.harpia` + `HarpiaTest/Include/file3.harpia` exercise every
construct and are the best worked example.

---

## 4. The compliance profile (`project.harpia.yaml`)

Optional, repo-root (or `HARPIA_COMPLIANCE_CONFIG=<path>`). Absent file or
omitted field falls back **per-field to the strictest value**.

```yaml
risk_class: class_b          # class_a | class_b | class_c   (IEC 62304)
topology: networked          # standalone | networked | cloud_connected
phi_handling: opt_in         # none | opt_in | required
jurisdiction: [US, EU]       # free-form; feeds the compliance report only
project: clinic              # owner key for public/private DB segregation (default "default")
```

`risk_class: class_c` **or** `topology: cloud_connected` flips the project into
**hardened transport**, which changes what several stages emit:

| Not hardened | Hardened |
|---|---|
| REST `X-User`/`X-Pswd`, SOAP `<credentials>`, gRPC `x-user`/`x-pswd` metadata | `admin`/`main`/`guest` **RBAC** on the verified mTLS client-cert CN, + `Authorization: Bearer` session tokens |
| generated HTTP/gRPC server bring-up runs insecure | bring-up requires + verifies client certs (`harpia_{http,grpc}_mtls.h`), plaintext refused |
| ZMQ CURVE is encryption-only | CURVE also enforces a **ZAP client-key allowlist** (`HARPIA_ZMQ_ALLOWLIST`) |
| standard crypto backend | FIPS crypto backend |

---

## 5. What gets generated

Every run writes a complete **C++ project** into the output folder. A Java or
Python target (§5.1) adds its own `java/` or `python/` project **next to** it,
in the same folder. `<hash>` in a file name is the md5 of your root
`.harpia` file's text (`users_<hash>_crudl.h`), so file names change when the
root file changes.

```
my_project/                     # <output_folder>
├── CMakeLists.txt              # the C++ project; -DHARPIA_BUILD_TESTS=ON for the ctest suite
├── HOW_TO_BUILD.md             # written by run_harpia.sh only
├── vcpkg.json                  # Windows dependency manifest (§16)
├── Doxyfile  USAGE_EXCERPT.md  # `doxygen` target + its main page
├── cmake/                      # helper scripts (mTLS / CURVE / DDS-Security provisioning)
├── proto/                      # .proto files derived from your messages (+ *_service.proto)
├── database/                   # SQL schema per table message (<name>_<hash>_table.sql)
├── wsdl/                       # WSDL 1.1 per persisted message
├── modifier/  access_modifier/  database_access/   # per-message flag sidecars
├── build_metadata/             # crypto_backend.json (the chosen crypto backend)
├── client/  server/            # runnable demo apps
├── tests/                      # generated ctest suite (opt-in)
├── third_party/                # vendored: sqlite, tinyxml2, crow, asio, cyclonedds
├── generated/
│   ├── ComplianceReport/       # bom.json (CycloneDX SBOM), traceability.{json,md}, compliance_report*.md
│   └── cpp/                    # <-- the C++ sources you include (put this on your include path)
│       ├── protofiles/         # protobuf + gRPC C++ (compiled from proto/)
│       ├── db/                 # CRUDL DAOs (+ harpia_db_registry.h)
│       ├── migrate/            # schema-migration helpers
│       ├── dbio/               # DB <-> JSON/XML bulk import/export
│       ├── json/  xml/  yaml/  # per-format adapters
│       ├── serialize/          # unified to_string/from_string façade + phi redaction
│       ├── rest/  soap/        # HTTP CRUD (Crow) + SOAP-over-HTTP endpoint
│       ├── http/               # shared REST+SOAP server bring-up (mTLS when hardened)
│       ├── grpc/               # gRPC service impls + server bring-up
│       ├── zmq/                # ZeroMQ push/pull/stream transports
│       ├── events/             # in-process event/callback channels
│       ├── dds/                # DDS transports (only if a `dds` message exists)
│       ├── capability/         # message-type-set advertisement + negotiate()
│       ├── delivery/           # critical-message queue runtime (only if a `critical` transport message exists)
│       ├── crypto/             # KeyProvider + encrypted-column runtime (only if a `phi` column exists)
│       ├── zap/                # ZMQ ZAP allowlist runtime (only when hardened + CURVE)
│       └── sdc/                # WS-Discovery responder + participant descriptors
├── java/                       # only with HARPIA_GEN_LANG=java   (§5.2)
└── python/                     # only with HARPIA_GEN_LANG=python (§5.3)
```

The generated project builds on any machine with a C++17 toolchain +
protobuf/gRPC — it does **not** need the Harpia repo. Copy the folder and build.

### 5.1 Choosing the language target

`HARPIA_GEN_LANG` = `cpp` (default), `java` or `python`. `run_harpia.sh`
always generates C++ and does not forward `HARPIA_GEN_LANG` (nor
`HARPIA_DB_BACKEND` / `HARPIA_COMPLIANCE_CONFIG`), so for Java or Python run
`main.py` in the image. Paths are inside the container: the repo is mounted at
`/harpia`, so keep the input and output folders under the repo (e.g. `build/`)
or mount them yourself:

```sh
Docker/run.sh env HARPIA_GEN_LANG=python \
    HARPIA_INPUT_FILE=./HarpiaTest/test.harpia \
    HARPIA_INCLUDE_FOLDER=./HarpiaTest/Include \
    HARPIA_OUTPUT_DIR=/harpia/build/my_project \
    python3 main.py
```

### 5.2 Java target (`java/`) — a Gradle project

```
java/
├── build.gradle  settings.gradle          # protobuf + grpc plugins, JDBC drivers, JeroMQ
└── src/
    ├── main/
    │   ├── proto/protofiles/              # copies of proto/ with java_package com.harpia.generated
    │   └── java/com/harpia/
    │       ├── generated/                 # <-- generated per-message sources
    │       │   ├── db/<name>_dao.java     #   JDBC CRUDL DAO
    │       │   ├── rest/  soap/           #   HTTP endpoints (JDK HttpServer)
    │       │   └── zmq/<name>_zmq.java    #   JeroMQ factories
    │       └── runtime/                   # hand-written runtimes copied verbatim
    │           └── db/ json/ xml/ rest/ soap/ zmq/ grpc/   (JdbcBind, HarpiaJson, HarpiaXml, HarpiaGrpcTls, HarpiaSession, …)
    └── test/java/com/harpia/generated/test/<name>_Test.java   # generated JUnit 5 tests
```

The message classes themselves (`com.harpia.generated.<name>`) and the gRPC
stubs are produced by the protobuf Gradle plugin at **build** time from
`src/main/proto/` — they are not files in the output. Build with
`cd java && gradle build` (runs the generated JUnit tests too). Java has no
phi encryption, YAML, migration or DDS (see the module `CLAUDE.md` files).

### 5.3 Python target (`python/`) — an installable package

```
python/
├── pyproject.toml                         # deps + extras; mypy/ruff config
├── harpia_generated/                      # <-- generated per-message sources
│   ├── protofiles/<name>_<hash>_pb2.py(.pyi)  (+ _pb2_grpc.py for services)
│   ├── db/<name>_<hash>_dao.py   migrate/   dbio/
│   ├── rest/  soap/  grpc/  http/          # transports + server bring-up
│   ├── zmq/   dds/   events/   sdc/   capability/   serialize/
├── harpia_runtime/                        # hand-written runtimes copied verbatim
│   ├── db/  crypto/  compliance/  http/  dds/  capability/
│   └── json.py xml.py yaml.py zmq.py rbac.py session.py tls.py …
├── proto/harpia_generated/protofiles/     # the .proto copies the _pb2 modules were built from
├── tests/                                 # generated pytest suite (conftest.py + test_<name>_<hash>.py)
└── docs/                                  # Sphinx (conf.py, index.rst, api.rst)
```

Import as `harpia_generated.db.users_<hash>_dao` / `harpia_runtime.yaml`;
`pip install ./python` (or put `python/` on `PYTHONPATH`); run its tests with
`pytest python/tests`.

### 5.4 Where your files go — what to commit

- **Your sources** (the root `.harpia` + `Include/`) live in the input
  folder. Harpia also writes **`schema_registry/<root stem>/<message>.fieldmap`
  next to the root `.harpia`**: the frozen protobuf wire number of every field,
  so reordering, adding, removing or `renamed_from`-renaming fields keeps the
  existing numbers and old and new peers still parse each other's bytes.
  **Commit it with your `.harpia` files.** Deleting
  it renumbers fields on the next run and breaks wire compatibility with
  every already-deployed peer.
- **The output folder is generated.** Don't hand-edit it. Regenerate it, or
  commit it as a whole if you vendor it. Regeneration is write-if-different:
  unchanged files keep their mtime, and files of a removed or renamed message
  are pruned.
- **Your application code** lives outside the output folder and consumes it:
  C++ puts `<out>/generated/cpp` on the include path (§7); Java depends on the
  `java/` Gradle project (or its built jar); Python installs or imports
  `python/`.
- **Runtime files you create** (the `LocalKeyProvider` store and its `.shred`
  sidecar, mTLS/CURVE material from `cmake/` scripts, SQLite databases)
  belong to your deployment, not to the source tree or the output folder.
  Keep key material out of version control.

---

## 6. Building the generated project

```sh
cd my_project
cmake -S . -B build -DHARPIA_BUILD_TESTS=ON
cmake --build build -j
ctest --test-dir build --output-on-failure
```

Omit `-DHARPIA_BUILD_TESTS=ON` for just the demo client/server. Prerequisites
(all in the `harpia-build` image): CMake ≥ 3.13, a C++17 compiler, protobuf +
gRPC, OpenSSL, pthreads; Cyclone DDS + `ddscxx` if you use `dds` messages;
SOCI + a backend (`libsoci-dev` + `soci_sqlite3` / `soci_postgresql`).

---

## 7. Consuming the generated code from your own app

A complete runnable example is in
[`HarpiaTest/app_example/consumer/`](HarpiaTest/app_example/consumer/) — build it
against a project you generated, not against the Harpia repo:

```sh
./run_harpia.sh HarpiaTest /tmp/gen --no-build
cmake -S HarpiaTest/app_example/consumer -B /tmp/cb -DHARPIA_GEN=/tmp/gen
cmake --build /tmp/cb && /tmp/cb/consumer
```

**Your CMake** puts `<gen>/generated/cpp` on the include path, compiles the
message `*.pb.cc` you use, adds header-only `third_party/crow` + `third_party/asio`,
builds `third_party/tinyxml2`, and links `soci_core` + a backend, protobuf,
pthreads (and gRPC / libzmq / OpenSSL / cyclonedds as needed).

Generated identifiers are **md5-hash-qualified** — `users_<hash>_crudl.h`,
accessor `id_<hash>()` — the hash comes from your `.harpia` input and changes
when your definitions do. Substitute your real hash for `<hash>` below.

### 7.1 Database — CRUDL, FK, maps, repeated, pagination

```cpp
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include "db/users_<hash>_crudl.h"

::soci::session db(::soci::sqlite3, ":memory:");
harpia::db::users_dao dao(db);
dao.create_table();                          // + child tables for maps / repeated / FK

::users u;
u.set_id_<hash>(1);                          // ID is caller-assigned, set before create()
u.set_name("alice"); u.set_address("1 River Rd");
dao.create(u);

::users got;
dao.read(1, &got);                           // false if not found
got.set_address("2 River Rd"); dao.update(got);

std::vector<::users> all;
dao.list(&all);                              // unbounded
std::vector<::users> page;
dao.list(&page, /*offset=*/0, /*limit=*/25); // paginated overload
dao.remove(1);
```

Singular composed fields (`vip_users myUsers;`) persist/load the child through
its own DAO automatically; `map<K,V>` and `repeteable` fields cascade through
their `<table>__<field>` child tables — you just call `create` / `read` on the
parent.

### 7.2 JSON / XML / YAML / unified serialize

```cpp
#include "json/users_<hash>_json.h"
#include "serialize/users_<hash>_serialize.h"   // pulls in xml + yaml too

std::string j; ::harpia::json::to_json(u, &j);
::users back; ::harpia::json::from_json(j, &back);

using harpia::serialize::Format;
std::string s = harpia::serialize::to_string(u, Format::XML);   // JSON | XML | YAML
harpia::serialize::from_string(s, &back, Format::XML);
```

For a message with a `phi` field, `to_string` renders every `phi` value as
`[REDACTED]` in all three formats by default (§9).

### 7.3 REST (Crow)

```cpp
#include "rest/users_<hash>_rest.h"
crow::SimpleApp app;
harpia::rest::register_users(app, db, "/api/v1");     // GET/POST/PUT/DELETE /api/v1/users
app.port(8080).run();                                  // GET list honours ?limit=&offset=
```

**Not hardened:** every request must carry `X-User: users` + `X-Pswd: <hash>`
or it is `401`. **Hardened:** see §8 — requests carry a client cert or a bearer
token and are checked against the RBAC matrix.

Crow's `multithreaded()` serves requests on several threads, so a server with
more than one client should register over a connection pool rather than one
shared session (same rules as the gRPC pool in §7.5):

```cpp
harpia::rest::register_users(app, pool, "/api/v1", /*lease_timeout_ms=*/2000);
harpia::soap::register_users_soap(app, pool, "/soap", 2000);
// or, every binding at once on one app:
harpia::http_transport::HttpServer server(pool, "/api/v1", "/soap", mtls);
```

Each request borrows one session after the access gate; no free slot within
the timeout answers `503` "db pool exhausted" (SOAP: `503` + a Fault), a dead
connection that can't reconnect answers `503` "db reconnect failed".

### 7.4 SOAP

```cpp
#include "soap/users_<hash>_soap.h"
harpia::soap::register_users_soap(app, db, "/soap");   // POST /soap/users, <Body> = get|set|update|delete
```

Non-hardened SOAP gates on a `<credentials><user>users</user><pswd><hash></pswd></credentials>`
header. The transport-free parse (`harpia::soap::message_from_request`) is in
`soap/harpia_soap.h` if you want to reuse it.

### 7.5 gRPC

```cpp
#include "grpc/grpc_server_bringup.h"
harpia::grpc_transport::MtlsFiles mtls{"ca.pem", "server.pem", "server_key.pem"};

// one client at a time: every RPC shares this session (NOT thread-safe)
harpia::grpc_transport::GrpcServer server(db, "0.0.0.0:50051", mtls);

// many concurrent clients: each RPC borrows its own session from a pool
::soci::connection_pool pool(16);
for (std::size_t i = 0; i < 16; ++i) pool.at(i).open(::soci::postgresql, "host=... dbname=...");
harpia::grpc_transport::GrpcServer server(pool, "0.0.0.0:50051", mtls,
                                          /*lease_timeout_ms=*/2000);
server.wait();
```

`mtls` is used only when the project is hardened (mTLS required and verified);
otherwise the server is insecure. Or wire one service onto your own
`grpc::ServerBuilder`:

```cpp
#include "grpc/users_<hash>_grpc.h"
harpia::grpc_svc::users_service svc(pool);   // or svc(db)
builder.RegisterService(&svc);
```

**Connection pool** (`db/harpia_db_pool.h`, `harpia::db::PooledSession`). With a
pool, each RPC borrows exactly one session and always gives it back; a borrow
that waits longer than `lease_timeout_ms` fails the RPC with
`RESOURCE_EXHAUSTED` "db pool exhausted" instead of hanging; a dead connection
(server restart, `pg_terminate_backend`) is reconnected on borrow (or the RPC
fails `UNAVAILABLE` "db reconnect failed"); an exception mid-transaction is
rolled back before the session goes back. `streamSrc` gives the session back
before it streams, so a slow reader never holds a slot. Sizing is yours:
stay under PostgreSQL's `max_connections` (default 100) minus admin headroom —
each PostgreSQL connection is a server process, heavier on Windows. Tens of
connections serve hundreds of clients when calls are short; beyond that, put
PgBouncer in front. On PostgreSQL, the reconnect check pings the server once
per borrow. The borrow deadline runs on the monotonic clock, so wall-clock
steps (NTP, VM resume, WSL2 resync) don't cut waits short.

**SQLite under a pool.** Open it with the helper, on a file:

```cpp
#include <soci/sqlite3/soci-sqlite3.h>
::soci::connection_pool pool(4);
harpia::db::open_sqlite_pool(pool, 4, ::soci::sqlite3, "/var/lib/app/app.db",
                             /*busy_timeout_ms=*/5000);
harpia::grpc_transport::GrpcServer server(pool, "0.0.0.0:50051", mtls);
```

It sets `PRAGMA journal_mode=WAL` (readers don't block the writer) and
`PRAGMA busy_timeout` on every connection, so concurrent writers wait instead
of failing with "database is locked". SQLite still runs one writer at a time;
for many concurrent writers use PostgreSQL. A pool of `:memory:` connections is
refused with `std::invalid_argument` (each would be its own empty database);
use a file, or the single-session constructor for an in-memory database.

**Shared state is thread-safe.** Besides its pooled session, a handler touches
the key provider (phi DAOs), the audit sink, the RBAC map and the session
revocation list. All harpia-shipped ones are safe to share across handler
threads. A `KeyProvider`, `KmsClient` or `AuditSink` you write yourself is
called from many threads too, so it must be thread-safe.

RPCs map `push`→create, `pullByID`→read, `streamSrc`→list (paginated via the
request's `offset`/`limit`), `heartBeat`→echo. Under hardening `heartBeat` mints
a `harpia-session-token` when the call carries `harpia-issue-session` metadata,
and data RPCs accept `authorization: Bearer <token>`.

### 7.6 ZeroMQ — push/pull

```cpp
#include "zmq/data_<hash>_zmq.h"
zmq::context_t ctx{1};

harpia::zmq_transport::data_receiver rx(ctx, "tcp://*:5555");         // bind side
harpia::zmq_transport::data_sender  tx(ctx, "tcp://localhost:5555",   // connect side
                                       /*origin=*/0);                  // 0 => runtime-assigned for many-to-*
::data msg; msg.set_i(7);
tx.send(msg);                                                          // bool; stamps the origin id
::data in; rx.recv(&in);
```

`event`/`stream` messages get `*_publisher` / `*_subscriber` instead of
`*_sender` / `*_receiver` (PUB/SUB). CURVE keys are a trailing defaulted
argument — see §11.

### 7.7 Stream lifecycle

```cpp
#include "zmq/sensor_feed_<hash>_zmq.h"
harpia::zmq_transport::sensor_feed_stream st(ctx);

harpia::zmq_transport::StreamConfig cfg{"tcp://localhost:6000", /*topic=*/""};
if (st.setup(cfg) != harpia::zmq_transport::StreamStatus::OK) { /* bad config */ }

for (;;) {
    auto r = st.read(/*timeout_ms=*/500);          // never blocks
    if (r.status == harpia::zmq_transport::ReadResult::OK)      handle(r.message);
    else if (r.status == harpia::zmq_transport::ReadResult::TIMEOUT)  continue;
    else break;                                     // STOPPED or INVALID (watchdog / reclamation)
}
st.stop();                                          // idempotent; RAII also closes with LINGER=0
```

Two synchronous time-based teardowns latch `INVALID`: a stop-deadline watchdog
(`stop_deadline_ms` since the last usable message, default 30 s) and
dead-connection reclamation (`reclaim_after_ms` since any inbound frame,
default 60 s).

### 7.8 Events / callbacks

```cpp
#include "events/bed_state_<hash>_events.h"
auto& ch = harpia::events::bed_state_channel();

auto id = ch.subscribe([](const ::bed_state& s) { /* runs on a detached thread */ });
::bed_state s; s.set_bed_id(3); s.set_occupied(1);
ch.publish(s);                                      // returns immediately; callbacks run async
ch.unsubscribe(id);
```

`event[cached]` (or bare `event`) replays the last published value to a late
subscriber once; `event[not-cached]` retains nothing. A throwing callback is
isolated — it neither propagates nor terminates the process, and siblings still
run. For an `event` message that also owns a table, its DAO calls
`<name>_channel().publish(msg)` at the end of a successful `create()` /
`update()` automatically.

### 7.9 Critical messages — delivery guarantees

```cpp
#include "zmq/alarm_event_<hash>_zmq.h"
harpia::zmq_transport::alarm_event_publisher pub(ctx, "tcp://*:7000",
                                                 /*queue_capacity=*/128);
::alarm_event a; a.set_alarm_type("apnea"); a.set_severity(3);

pub.publish(a);          // does NOT hit the socket -- enqueues a CRC+seq Envelope, returns optional<PushOutcome>
// ... subscriber joins, or a transient outage clears ...
pub.flush();             // drains the queue to the wire oldest-first, stops at the first socket failure
pub.pending();           // how many are still queued
```

Queue overflow rotates the oldest entry and emits a `queue_rotated` audit
record — never a silent drop. Non-`critical` senders keep the plain
`bool send()` API.

---

## 8. Hardened transport (mTLS + RBAC + sessions)

Enabled by `risk_class: class_c` or `topology: cloud_connected` in
`project.harpia.yaml` (§4). Deployment config, read at startup, **not** compiled
in:

| env var | file format |
|---|---|
| `HARPIA_RBAC_MAP` | `<cert-CN> <role>` per line — role ∈ `admin` / `main` / `guest` |
| `HARPIA_SESSION_KEY` | the HMAC key (raw, or `@<path>`); empty ⇒ sessions disabled |
| `HARPIA_SESSION_TTL` | token lifetime in seconds (default 900) |
| `HARPIA_SESSION_REVOCATIONS` | one revoked `jti` per line, re-read on change |
| `HARPIA_ZMQ_ALLOWLIST` | `<z85-client-public-key> <identity>` per line — deny-all if absent. `#` starts a comment only as the first character of a line's first token or of the identity; `#` inside a key is part of the key (it is a Z85 digit) |

Bring the servers up with the generated helpers, which pick mTLS credentials
automatically when hardened:

```cpp
harpia::http_transport::HttpServer http;              // REST + SOAP on one crow::SimpleApp
http.Configure(/*rest_base=*/"/api", /*soap_base=*/"/soap", db);
http.Run(8443);                                        // client cert required + verified; plaintext refused

harpia::grpc_transport::GrpcServer grpc;
grpc.Start("0.0.0.0:50051");
```

Provision a dev PKI with `Assets/cmake/mtls_provision.sh <out_dir> [server_CN] [identity ...]`.
For a server on another machine add `--san <ip-or-hostname>` (repeatable; e.g.
the LAN address, or `10.0.2.2` for the Android emulator). For many clients pass
`--clients-file <file>` (one `<identity> <role>` per line, role `admin|main|guest`):
one client cert per identity plus a ready `rbac_map.txt` for `HARPIA_RBAC_MAP`.
Re-runs reuse the CA and keep existing identities (only new ones are issued).
A **Java / Android client** of a hardened C++ server opens its channel with
the generated `com.harpia.runtime.grpc.HarpiaGrpcTls` (works with
`grpc-netty-shaded` and `grpc-okhttp`; PEMs as `InputStream`s, key in PKCS#8):

```java
ChannelCredentials creds = HarpiaGrpcTls.credentials(caPem, clientCertPem, clientKeyPem);
ManagedChannel ch = Grpc.newChannelBuilderForAddress("station", 50051, creds).build();

// optional bearer session (com.harpia.runtime.grpc.HarpiaSession)
HarpiaSession s = HarpiaSession.issue(ch, users_ServiceGrpc.getHeartBeatMethod());
var stub = users_ServiceGrpc.newBlockingStub(ch).withInterceptors(s.interceptor());
s.withRetry(() -> stub.push(msg));   // re-issues once if the token expired
```
 Clients
obtain a token from `POST <rest_base>/session` (REST/SOAP) or `heartBeat` +
`harpia-issue-session` metadata (gRPC), then present `Authorization: Bearer
<token>` — the token's CN, not the cert, is the identity for that call. The RBAC
matrix is fixed: admin = every verb, main = every verb but delete, guest =
read/list/stream, heartbeat open to all. Each denial is one value-free audit
record (`rbac_denied` / `session_denied` / `zap_denied`).

### 8.1 Per-message override: `protected` / `open`

The compliance profile picks one project-wide default, but a single message
can override it (message-level-hardening epic, protected-open-modifiers):

```
protected message alarm_event { ... } alarm_event_table;  // always RBAC-gated
open message catalog { ... } catalog_table;                // always the flat gate
```

- `protected message` — this message's REST/SOAP/gRPC endpoints always use
  the RBAC/session gate above, even in a project whose compliance profile
  does not request hardening.
- `open message` — this message's endpoints always use the flat
  `X-User`/`X-Pswd`-style credential (Stage 5), even in an otherwise-hardened
  project. This is a downgrade to that credential, not "no check at all" —
  a caller still needs it, it just never needs a client certificate.
- Both on the same message is a generation-time error — fix the schema, it
  is never silently resolved one way or the other.
- A message using neither modifier is unaffected: it inherits whatever the
  project's compliance profile already decides, byte-identically to before
  this feature existed.
- **Scope**: the REST/SOAP/gRPC RBAC/session axis only. ZMQ CURVE key
  distribution and DDS-Security participant identity stay project-wide
  (§11, §12) — a later epic, not yet per-message.
- **No composition propagation**: a message's own `protected`/`open` is the
  only input to its own gate. If a `protected` message composes another
  message that has its own independent table (and therefore its own
  independent endpoints), that composed message is NOT automatically
  protected too — mark it explicitly if it needs to be. Losing protection
  this way is a schema-authoring decision harpia does not infer or block.
- **A `protected` message in an otherwise-unhardened project, or an `open`
  message in an otherwise-hardened one, changes that project's transport,
  not just the one message.** Crow/gRPC serve one listening socket per
  project, so "TLS on for this route only" isn't possible at the transport
  layer; instead the whole project's REST/SOAP/gRPC transport switches to
  "client certificate requested, but not required" (confirmed feasible and
  proven live in `UnitTests/test_mtls_optional_mode_spike.py`) — every other
  message's own gate keeps enforcing its own requirement regardless. A
  `protected` message under an unhardened default additionally needs real
  mTLS PEM files supplied at runtime (the same `MtlsFiles`/env-driven
  provisioning as §8 above) even though the project itself isn't
  "hardened" — without them the generated code refuses to start rather than
  silently serving that message in the clear.

---

## 9. `phi` fields — encryption, redaction, audit

**Current cipher is a placeholder, not a real one.** The envelope-encryption
machinery below (KEK/DEK separation, rotation, per-DEK crypto-shred,
zeroization, audit-on-access) is real, but the actual `Dek::seal`/`open` step
it wraps is an XOR placeholder (`Crypto/backend.py`'s `CryptoBackend` seam
exists, but no backend has a real cipher bound to it yet). **Do not rely on
this for confidentiality of real PHI today** — treat "at rest" below as
describing the envelope and audit trail a real cipher will drop into, not
current ciphertext strength.

Tag a field `phi` and, with **no other change to your code**:

- **at rest** — the DAO encrypts it on `create`/`update` and decrypts on
  `read`/`list`. The DAO's constructor takes a
  `::harpia::crypto::KeyProvider&` (defaulted to
  `::harpia::crypto::default_key_provider()`); pass a real one for persistent
  keys:

  ```cpp
  #include "crypto/harpia_key_provider_local.h"
  harpia::crypto::LocalKeyProvider kp("/var/lib/app/keks");   // KEK rotation, per-DEK crypto-shred
  harpia::db::patient_vitals_dao dao(db, kp);
  ```

  An unrecoverable value decrypts to the type's default (0 / "") — never a
  throw.

  The local key store (and its `<path>.shred` sidecar) is written owner-only
  (`0600`) on POSIX. A store whose mode lets group or others read it is
  **refused**: the constructor throws `LocalKeyStoreInsecure` (Python raises
  the same-named error). If that happens, assume the keys may have been read:
  rotate, then `chmod 0600` the files. A `phi` column is always TEXT in the
  DDL; the generated migration retypes an older numeric `phi` column.

- **in serialization** — `harpia::serialize::to_string(msg, fmt)` renders every
  `phi` value as `[REDACTED]` in JSON, XML and YAML. Redacted output is a lossy
  view, not a round-trip format. The sanctioned, audited opt-out:

  ```cpp
  #include "serialize/harpia_redaction_audit.h"
  harpia::redaction::allow_phi_print(sink, "operator debugging alarm pipeline");
  // ... real values now render ...
  harpia::redaction::restore_phi_redaction(sink);
  ```

- **on access** — every `phi` CRUDL op, event dispatch, DDS publish and
  redaction opt-out emits exactly one `AuditSink::record(op, subject, detail)`
  with metadata only. Inject your own sink (defaulted to a no-op) through the
  DAO / channel constructor; the record's signature structurally cannot carry a
  field value.

A message with no `phi` field is byte-for-byte what it would be without the
feature.

---

## 10. Schema migration + cross-version data transforms

Each table message gets `migrate_<name>(db)` in
`migrate/<name>_<hash>_migrate.h` that brings an older live database to the
current schema — column and child-table **rename / add / drop / retype** are all
inferred from the `.harpia` alone (`renamed_from[old]` drives the rename).

What harpia can't infer is a value **derivation**. For that,
`migrate_<name>` takes an optional `data_transform` hook that runs **after** the
add step and **before** the drop step:

```cpp
harpia::db::migrate_users(db, [](::soci::session& db) {
    db << "UPDATE \"user_table\" SET \"age\" = ... WHERE \"age\" IS NULL";
});
```

Make it idempotent (guard with `WHERE`) — it may run on every startup.

---

## 11. ZeroMQ CURVE encryption

Every generated ZMQ constructor takes a trailing, defaulted curve-keys struct —
pass nothing for plaintext:

```cpp
harpia::zmq_transport::CurveServerKeys sk{server_secret_z85};                 // bind side
harpia::zmq_transport::data_receiver rx(ctx, "tcp://*:5555", sk);

harpia::zmq_transport::CurveClientKeys ck{server_public_z85,                  // connect side
                                          client_public_z85, client_secret_z85};
harpia::zmq_transport::data_sender tx(ctx, "tcp://host:5555", 0, ck);
```

Keys are Z85 text (`zmq_curve_keypair()`'s native form). CURVE is a no-op over
`inproc://`; `tcp://` and `ipc://` go through the real handshake. When the
profile is hardened, bind-side `CURVE_SERVER` sockets additionally enforce the
`HARPIA_ZMQ_ALLOWLIST` (§8) — an unknown client key is rejected at the handshake
even with valid crypto; `Assets/cmake/zmq_zap_provision.sh <out_dir> [identity ...]`
mints a starter allowlist (`--clients-file <file>`: the same identity file
`mtls_provision.sh` takes, one CURVE keypair per identity; re-runs keep existing
keys).

**`ZMQ_LINGER`:** a socket with an undelivered message from a failed handshake
blocks forever on destruction (`LINGER == -1`). If a sender might face a peer
that fails to authenticate, set
`sender.socket().set(zmq::sockopt::linger, 0)`.

---

## 12. DDS transport

Add `dds` to a message and it also gets a Cyclone DDS publisher/subscriber in
`generated/cpp/dds/`, with QoS from the schema: `critical` → RELIABLE +
KEEP_ALL + RESOURCE_LIMITS, otherwise BEST_EFFORT + KEEP_LAST(1). DDS-Security is
wired through the same `CryptoBackend` seam as mTLS — a `secured_participant`
refuses to come up plaintext (`SecurityRefused`), with a strict
`security/governance.xml` and a per-schema `security/permissions.xml`. Provision
certs with `Assets/cmake/dds_security_provision.sh`. A `phi` field crossing DDS
emits one value-free `phi_publish` audit record per publish.

---

## 13. Database backend (SQLite / PostgreSQL)

The persistence layer is emitted against [SOCI](https://soci.sourceforge.io/) —
the same generated C++ runs on SQLite (default) or PostgreSQL. Pick the SQL
dialect at generation time:

```sh
HARPIA_DB_BACKEND=postgresql python3 main.py
```

Only the emitted SQL changes; every DAO / handler / migration takes a
`soci::session&`. Choose the backend where you open it:

```cpp
::soci::session db(::soci::sqlite3, ":memory:");
// ::soci::session db(::soci::postgresql, "host=… dbname=… user=… password=…");
```

Install `libsoci-dev` + `soci_sqlite3` / `soci_postgresql` on the target (not
vendored). On Windows, `vcpkg.json` requests `soci[sqlite3,postgresql]` — one
`SOCI::SOCI` target links both (§16).

---

## 14. Compliance artifacts

Every generation writes `generated/ComplianceReport/`:

- **`bom.json`** — a CycloneDX 1.5 SBOM: vendored component versions, toolchain
  versions, and six `harpia:git_*` provenance properties (commit, ref, dirty,
  describe, origin URL, parent commit).
- **`traceability.{json,md}`** — a requirement catalog mapped to the code and
  tests satisfying each entry.
- **`compliance_report[.<jurisdiction>].md`** — per-jurisdiction document shells
  over the same evidence (driven by `jurisdiction:` in `project.harpia.yaml`).

These are informational build outputs — nothing in the generated project depends
on them at build time.

---

## 15. Other entry points

```sh
Docker/run.sh                    # interactive shell in the harpia-build image
Docker/run.sh pytest             # Harpia's own test suite
Docker/run.sh python3 main.py    # the pipeline with in-repo defaults
```

`main.py` env overrides: `HARPIA_INPUT_FILE`, `HARPIA_INCLUDE_FOLDER`,
`HARPIA_OUTPUT_DIR`, `HARPIA_DB_BACKEND`, `HARPIA_COMPLIANCE_CONFIG`,
`HARPIA_CRYPTO_BACKEND`.

---

## 16. Notes & limits

- Regeneration is **write-if-different** — an unchanged file keeps its mtime, a
  renamed/removed message has its old files pruned. **Never hand-edit generated
  files.**
- Exactly one root `.harpia` per input folder (imports under `Include/`).
- Message ids (`ID_*` primary key) are **caller-assigned** — set them before
  `create()`.
- The generator (`main.py`) runs only on Linux/Docker. The **generated C++
  project** builds natively on Windows (MSVC 2022 + vcpkg) — verified for the
  ZMQ demo (incl. `-DUSE_ZMQ_CURVE=ON`), the REST/JSON consumer
  (incl. `-DUSE_TLS=ON`), the PostgreSQL backend (`-DUSE_POSTGRES=ON`, against a
  live server), and the Stage 14 `ctest` suite. Use a standalone vcpkg clone and
  pass `-DCMAKE_TOOLCHAIN_FILE=…/vcpkg/scripts/buildsystems/vcpkg.cmake`;
  `vcpkg.json` (shipped in every generated project) declares `protobuf`, `grpc`,
  `zeromq[curve,sodium]`, `cppzmq` and `soci[sqlite3,postgresql]`. Freshly-built
  unsigned network executables can trip antivirus heuristics — exclude the build
  folder if a relink fails with `LNK1104` right after a run.
