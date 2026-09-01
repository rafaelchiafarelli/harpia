# Using Harpia

Harpia is a **code generator**: you write a `.harpia` definition file describing
your messages, and Harpia emits a self-contained, compilable C++ project with the
persistence, serialization and transport layers already wired up.

You do not need to modify anything inside the Harpia repository to use it — treat
Harpia as a **black box**: give it a `.harpia` file, get a buildable C++ project
out. This document is the consumer's guide to that flow.

> For *what each pipeline stage does internally*, see `harpia.process.md` (the
> spec) and `README.md` (the current-status table). This file is about **using**
> the generator, not extending it.

---

## 1. Quick start

The one command that does everything — generate, build and test:

```sh
./run_harpia.sh <input_folder> <output_folder>
```

Example, using the bundled sample input:

```sh
./run_harpia.sh HarpiaTest /tmp/my_project
```

This runs the whole pipeline inside the `harpia-build` Docker image (so you need
nothing installed on the host but Docker), writes a **self-contained C++ project**
into `/tmp/my_project`, then builds it and runs its generated unit tests. When it
finishes you'll see `ctest` report all tests passing and:

```
generated project (portable example): /tmp/my_project
build instructions: /tmp/my_project/HOW_TO_BUILD.md
```

Add `--no-build` to generate only (skip the cmake build + ctest):

```sh
./run_harpia.sh HarpiaTest /tmp/my_project --no-build
```

Both folders may live **anywhere** on disk. The output folder is regenerated
write-if-different (see §11) — safe to point at the same folder across runs;
it is not wiped first.

---

## 2. The input folder

`run_harpia.sh` expects an input folder containing **exactly one** root `.harpia`
file, plus an optional `Include/` subfolder holding modules that the root file
imports:

```
HarpiaTest/
├── test.harpia          # the one root definition file
└── Include/             # optional — modules pulled in via `import "..."`
    ├── file1.harpia
    ├── file2.harpia
    └── file3.harpia
```

The root file imports modules by name:

```
import "file1.harpia";
```

---

## 3. The `.harpia` language (by example)

A `.harpia` file declares **messages** and **enums**. A message that ends with a
table name is persisted to the database; the transport/role qualifiers before
`message` control which surfaces are generated for it.

```harpia
// an enum
enum grower {
    g_a;
    g_b;
    g_c = 14;      // explicit value
    g_d;
    g_e = 0;       // one enumerator must be 0
}

// a plain (non-persisted) message: no table name after the closing brace
message prince {
    int var;
    optional int val;                          // optional field
    required map<string,int> b;                // required + a map field
    repeteable int scores;                     // a repeated field
};

// a persisted message: note the transport qualifiers and the trailing table name
stream pull push event message data {
    int i;
    optional int j;
    prince val;                // composed field (embeds another message)
    grower car;                // enum-typed field
    repeteable int tags;       // repeated scalar
} table_data;                  // <-- table name => this message is persisted

// messages can nest, and reference each other (1-to-1 and 1-to-many)
stream pull push event message top_users {
    string sponsor;
    required string name;
    event message vip_users {
        optional string name;
        string family;
    } table_vip_users;
    vip_users myUsers;             // singular composed reference (FK)
    repeteable vip_users members;  // repeated composed reference (1-to-many)
} user_table;
```

Building blocks you can use:

| Construct | Meaning |
|---|---|
| `import "file.harpia";` | pull in another module (from `Include/`) |
| `enum Name { a; b = 3; }` | an enumeration (one enumerator must be `0`) |
| `message Name { … };` | a plain message (serialized, not persisted) |
| `… message Name { … } table_name;` | a **persisted** message backed by `table_name` |
| `int` / `string` | scalar field types |
| `map<K,V>` | a map field (persisted in a child table) |
| `OtherMessage field;` | a composed field (embed / foreign key) |
| `optional` / `required` | field presence modifiers |
| `repeteable` | a repeated field (persisted in an ordinal child table) |
| `pagination[N]` | a bounded-size hint on a field |
| `renamed_from[old_name]` | this field replaced `old_name` in an earlier schema version — `migrate_<name>` renames the live column instead of dropping and re-adding it |
| `stream` / `pull` / `push` / `event` | transport/role qualifiers on a message |

> The full grammar and the semantics of each qualifier live in
> `harpia.process.md`. The sample `HarpiaTest/test.harpia` exercises every
> construct above and is the best worked example.

---

## 4. What gets generated

The output folder is a **complete, portable C++ project**:

```
my_project/
├── CMakeLists.txt          # top-level build (opt-in tests via -DHARPIA_BUILD_TESTS=ON)
├── HOW_TO_BUILD.md         # build instructions, generated per project
├── proto/                  # the .proto files derived from your messages
├── generated/cpp/
│   ├── protofiles/         # protobuf/gRPC C++ (compiled from proto/)
│   ├── db/                 # CRUDL data-access objects (create/read/update/remove/list)
│   ├── migrate/            # schema-migration helpers (add/rename/drop columns)
│   ├── dbio/               # DB <-> JSON/XML bulk import/export
│   ├── json/               # message <-> JSON adapters
│   ├── xml/                # message <-> XML adapters (+ XSD)
│   ├── rest/               # REST HTTP CRUD bindings (Crow), credential-gated
│   ├── soap/               # SOAP-over-HTTP endpoint (Crow + tinyxml2)
│   ├── grpc/               # gRPC service implementations (backed by CRUDL)
│   └── zmq/                # ZeroMQ push/pull transport
├── database/               # the generated SQL schema (CREATE TABLE …)
├── wsdl/                   # WSDL 1.1 descriptor per persisted message
├── client/  server/        # a runnable demo client + server
├── tests/                  # generated C++ unit + app-level tests (CTest)
└── third_party/            # vendored deps: sqlite, tinyxml2, crow, asio
```

Because `third_party/` is vendored in-tree, the generated project builds on any
machine with a C++17 toolchain + protobuf/gRPC — **it does not need the Harpia
repo**. Copy the folder to a target board and build it there.

---

## 5. Building the generated project

`run_harpia.sh` already builds and tests it for you. To build it yourself later
(the steps are also in the project's own `HOW_TO_BUILD.md`):

```sh
cd my_project
cmake -S . -B build -DHARPIA_BUILD_TESTS=ON
cmake --build build -j
ctest --test-dir build --output-on-failure
```

Omit `-DHARPIA_BUILD_TESTS=ON` to build just the demo client/server without the
generated test suite.

**Prerequisites** (all present in the `harpia-build` Docker image):
- CMake ≥ 3.13 and a C++17 compiler
- Protocol Buffers + gRPC (`protoc`, `grpc_cpp_plugin`, dev libs)
- pthreads

The REST and SOAP surfaces are **credential-gated**: every request must carry the
generated access credential (`X-User` / `X-Pswd` headers for REST; a
`<credentials>` SOAP header for SOAP), or it is rejected with `401`.

---

## 6. Wiring the generated code into your own project

Beyond building the generated project standalone, you usually want to **consume**
its code from your own application. A complete, runnable example lives in
[`HarpiaTest/app_example/consumer/`](HarpiaTest/app_example/consumer/) — inspect it end to end:

- [`HarpiaTest/app_example/consumer/src/main.cpp`](HarpiaTest/app_example/consumer/src/main.cpp) — the app.
- [`HarpiaTest/app_example/consumer/CMakeLists.txt`](HarpiaTest/app_example/consumer/CMakeLists.txt) — the build wiring.
- [`HarpiaTest/app_example/consumer/README.md`](HarpiaTest/app_example/consumer/README.md) — how to run it.

It depends only on a project you generated (via `-DHARPIA_GEN=<generated dir>`),
not on the Harpia repo:

```sh
./run_harpia.sh HarpiaTest /tmp/gen --no-build          # generate
cmake -S HarpiaTest/app_example/consumer -B /tmp/cb -DHARPIA_GEN=/tmp/gen
cmake --build /tmp/cb && /tmp/cb/consumer               # build + run
```

**What your code calls** (from `main.cpp`): open a `soci::session`, then use the
generated headers directly —

```cpp
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include "db/users_<hash>_crudl.h"     // CRUDL DAO
#include "json/users_<hash>_json.h"    // JSON adapter
#include "rest/users_<hash>_rest.h"    // REST bindings

::soci::session db(::soci::sqlite3, ":memory:");
harpia::db::users_dao dao(db);              // create/read/update/remove/list
dao.create_table();
::users u; u.set_id_<hash>(1); u.set_name("alice"); dao.create(u);

std::string j; ::harpia::json::to_json(u, &j);   // serialize

crow::SimpleApp app;                        // expose it over HTTP
harpia::rest::register_users(app, db, "/api/v1");
app.port(8080).run();                       // GET/POST/PUT/DELETE /api/v1/users
```

**What your `CMakeLists.txt` wires** (see the example): put `<gen>/generated/cpp`
on the include path; compile the message `*.pb.cc` you use; add the vendored
`third_party/crow` + `third_party/asio` (header-only) and build
`third_party/tinyxml2`; link `soci_core` + the backend (`soci_sqlite3` /
`soci_postgresql`), protobuf, and pthreads.

Note the generated identifiers are **md5-hash-qualified** (`users_<hash>_crudl.h`,
accessor `id_<hash>()`) — the hash comes from your `.harpia` input, so it changes
when your definitions do.

**Schema migration and cross-version data transforms:** each table-bearing
message also gets a `migrate_<name>(db)` (`migrate/users_<hash>_migrate.h`)
that brings an older live database up to the current schema — column
rename/add/drop/retype are all handled automatically from the `.harpia`
definition alone (see [`Database/CLAUDE.md`](Database/CLAUDE.md)). What
harpia *can't* infer automatically is a value **derivation** — e.g. filling
a new column from an old one, or splitting one retiring column into several
new ones — since that requires knowing what the data *means*, not just
where it lives. For that, `migrate_<name>` takes an optional
`data_transform` hook:

```cpp
harpia::db::migrate_users(db, [](::soci::session& db) {
    // runs AFTER the add step (so any new destination column already
    // exists) and BEFORE the drop step (so an old source column being
    // retired is still there to read) -- e.g. deriving `age` from a
    // `birthdate` column, or splitting a retiring `full_name` into new
    // `first_name`/`last_name` columns.
    db << "UPDATE \"user_table\" SET \"age\" = ... WHERE \"age\" IS NULL";
});
```

Pass nothing for today's behavior (no transform runs) — the parameter
defaults to an empty `std::function`. Write your lambda to be idempotent
(e.g. guard it with a `WHERE` clause, as above) since `migrate_<name>` may
run on every application startup, not just once.

---

## 7. Other ways to run it

`run_harpia.sh` is the recommended entry point. Two lower-level options:

**Interactive / scripted, inside the toolchain image:**
```sh
Docker/run.sh                    # interactive shell in the harpia-build image
Docker/run.sh pytest             # run Harpia's own test suite
Docker/run.sh python3 main.py    # run the pipeline with the in-repo defaults
```

**Directly via `main.py`** (defaults generate the in-repo `HarpiaTest` example).
Override the paths with environment variables:

| Variable | Meaning |
|---|---|
| `HARPIA_INPUT_FILE` | path to the root `.harpia` file |
| `HARPIA_INCLUDE_FOLDER` | folder of importable modules |
| `HARPIA_OUTPUT_DIR` | where to write the generated project (write-if-different; safe to reuse across runs) |
| `HARPIA_DB_BACKEND` | database dialect: `sqlite` (default) or `postgresql` |

---

## 8. Choosing the database backend

The persistence layer is **database-agnostic**: the generated data-access code is
emitted against [SOCI](https://soci.sourceforge.io/), so the same project runs on
**SQLite** (default) or **PostgreSQL**. Pick the dialect at generation time:

```sh
HARPIA_DB_BACKEND=postgresql python3 main.py
```

Only the emitted SQL dialect changes (column types, `CREATE TABLE`, migration
introspection, version-stamp upsert). The C++ API is identical — every DAO,
REST/SOAP/gRPC handler and the migration take a `soci::session&`. At the one place
you open that session, choose the backend:

```cpp
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>        // or soci/postgresql/soci-postgresql.h
::soci::session db(::soci::sqlite3, ":memory:");
// PostgreSQL: ::soci::session db(::soci::postgresql,
//                                "host=... dbname=... user=... password=...");
harpia::db::users_dao dao(db);                // same DAO either way
```

**Build/runtime deps for the DB layer:** SOCI core + the backend
(`soci_core` + `soci_sqlite3` or `soci_postgresql`), which link the system SQLite
/ libpq. These come from the system package manager (like protobuf/gRPC/ZMQ), not
vendored in-tree — install `libsoci-dev` + the relevant backend package on the
target.

**On Windows (vcpkg — see [§12](#12-building-on-windows)):** `Assets/vcpkg.json`
requests `soci[sqlite3,postgresql]`, so both backends are available from the same
manifest; no separate install step. vcpkg's `soci` port exports one CONFIG
target, `SOCI::SOCI`, that links every backend feature you installed — link it
once, same for either backend:

```
find_package(SOCI CONFIG REQUIRED)
target_link_libraries(your_target PRIVATE SOCI::SOCI)
```

`SOCI::SQLite3`'s own link interface references `SQLite3::SQLite3` without
importing it, needing a hand-written alias (see the `HarpiaTest/app_example/consumer`/Stage 14
`gen_tests` CMakeLists for the pattern). `SOCI::PostgreSQL` does **not** need an
analogous alias: vcpkg's `libpq` port ships a `vcpkg-cmake-wrapper.cmake` that
hooks CMake's builtin MODULE-mode `find_package(PostgreSQL)` and defines
`PostgreSQL::PostgreSQL` directly, so a plain `find_package(PostgreSQL REQUIRED)`
before `find_package(SOCI CONFIG REQUIRED)` is enough — see
`HarpiaTest/app_example/consumer/CMakeLists.txt`'s `USE_POSTGRES` option. Build- and
live-session-verified on Windows (MSVC + vcpkg, real `soci::postgresql`
session against a real server) — see [§12](#12-building-on-windows).

---

## 9. Enabling TLS on REST/SOAP/gRPC

Harpia generates route registration (`RestAdapter`/`SoapAdapter`) or the service
class (`GrpcServiceAdapter`) — it never generates the server-construction call
(`app.port().run()`, `grpc::ServerBuilder::BuildAndStart()`). That's caller code,
same as the `soci::session` in [§8](#8-choosing-the-database-backend) — so TLS is
something **you** turn on where you build your own server, not a generation-time
flag.

**REST/SOAP (Crow):** the vendored `third_party/crow/crow.h` already has full SSL
support, gated behind `CROW_ENABLE_SSL`:

```cpp
#define CROW_ENABLE_SSL     // before including crow.h anywhere in this TU
#include "crow.h"
...
crow::SimpleApp app;
harpia::rest::register_users(app, db, "/api/v1");
app.ssl_file("server.crt", "server.key");   // must be set before .run()/.run_async()
app.port(8443).run();
```

Link OpenSSL (`find_package(OpenSSL REQUIRED)`, `target_link_libraries(... OpenSSL::SSL
OpenSSL::Crypto)`) and supply a cert/key — a self-signed pair is enough for
development (`openssl req -x509 -newkey rsa:2048 -nodes -keyout server.key -out
server.crt -days 365 -subj "/CN=localhost"`); use a CA-issued pair in production.

**gRPC:** swap `grpc::InsecureServerCredentials()` for
`grpc::SslServerCredentials(...)` where you build your `grpc::ServerBuilder` —
`libgrpc++-dev` already ships this, no extra linking needed:

```cpp
grpc::SslServerCredentialsOptions opts;
opts.pem_key_cert_pairs.push_back({read_file("server.key"), read_file("server.crt")});
builder.AddListeningPort(addr, grpc::SslServerCredentials(opts));
```

**Worked example:** [`HarpiaTest/app_example/consumer/`](HarpiaTest/app_example/consumer/) demonstrates the
Crow path end to end — build it with `-DUSE_TLS=ON` to see a generated CMake
target generate a self-signed cert at configure time and serve real REST traffic
over it (see its README).

---

## 10. Enabling CURVE encryption on ZMQ

Unlike REST/SOAP/gRPC, ZMQ's `bind()`/`connect()` happen **inside** the
generated sender/receiver classes themselves (`ZmqAdapter`'s
`sender.tmpl`/`receiver.tmpl`), so "enabling encryption" here isn't a pure
caller-side build flag the way TLS is in [§9](#9-enabling-tls-on-restsoapgrpc)
— the generated constructors carry an extra, optional parameter for it.

CURVE itself is **encryption-only**: any client presenting valid CURVE crypto
is accepted, the ZMQ analogue of TLS with no client certificates. On top of
that, when the compliance profile mandates hardened transport
(`transport_hardening_required` — the same predicate that turns on mTLS for
REST/SOAP/gRPC), the generated `CURVE_SERVER` sockets add a **ZAP client-key
allowlist** (transport-authn epic): the bind-side constructors call
`::harpia::zap::ensure_running(ctx)` (`generated/cpp/zap/harpia_zap.h`), which
runs a ZAP handler on `inproc://zeromq.zap.01` that checks each client's public
key against the file named by the `HARPIA_ZMQ_ALLOWLIST` env var — one
`<z85-client-public-key> <identity>` per line, `#` comments — and rejects an
unknown key at the handshake even when its CURVE crypto is valid. **Fail-safe:
with no allowlist file (or an empty one) every key is denied.** Each rejection
emits one value-free `AuditSink` `"zap_denied"` record (the z85 key + identity,
never secret material). `Assets/cmake/zmq_zap_provision.sh <out_dir> [id ...]`
mints a server keypair + client identities and writes a starter allowlist.
Without hardening, CURVE stays purely wire encryption, no allowlist.

Every generated sender/receiver/publisher/subscriber constructor takes a
trailing, defaulted curve-keys struct — pass nothing and you get exactly
today's plaintext behavior:

```cpp
// Bind side (PULL receiver / PUB publisher) -- CURVE "server" role, only
// needs its own secret key. CURVE_SERVER accepts any client with valid crypto.
harpia::zmq_transport::CurveServerKeys server_keys{server_secret_z85};
harpia::zmq_transport::users_receiver receiver(ctx, endpoint, server_keys);

// Connect side (PUSH sender / SUB subscriber) -- CURVE "client" role, needs
// the peer's public key plus its own keypair.
harpia::zmq_transport::CurveClientKeys client_keys{
    server_public_z85, client_public_z85, client_secret_z85};
harpia::zmq_transport::users_sender sender(ctx, endpoint, origin, client_keys);
```

Keys are Z85 text (`zmq_curve_keypair()`'s native output) — cppzmq's
`curve_*` sockopts accept that form directly, no binary decode needed. CURVE
is a no-op over `inproc://` (it bypasses the ZMTP wire protocol entirely);
`tcp://` and `ipc://` both go through the real handshake.

**Note on `ZMQ_LINGER`:** if a peer never completes the CURVE handshake (e.g.
a mismatched key), a socket with an outstanding send blocks on destruction by
default (`ZMQ_LINGER` is `-1`, "wait forever to flush"). If your code might
construct a sender against a peer that could fail to authenticate, set
`sender.socket().set(zmq::sockopt::linger, 0)` explicitly, or shutdown will
hang.

**Worked example:** `Assets/server_template`/`client_template` (the ZMQ demo)
gain `-DUSE_ZMQ_CURVE=ON`. No CLI keygen tool ships with apt's
`libzmq3-dev`, so the root `CMakeLists.txt` compiles+runs a tiny probe
(`cmake/curve_keygen_probe.cpp`, via `try_run`) at configure time to produce
a fresh ephemeral keypair per side, written to a generated
`harpia_zmq_curve_keys.h` (**not** a `target_compile_definitions` string —
Z85's alphabet includes characters like `#`/`$`/`(` that a build system's
command-line layer, e.g. Make's `#`-starts-a-comment / `$`-is-a-variable
handling, will silently corrupt). See `Assets/CLAUDE.md` for the mechanism.

On Windows, vcpkg's `zeromq` port needs the `curve`+`sodium` features (see
`Assets/vcpkg.json`); `-DUSE_ZMQ_CURVE=ON` is build- and run-verified there
(MSVC 2022 + vcpkg, real `tcp://` CURVE client/server exchange — see
[§12](#12-building-on-windows)).

---

## 11. Notes & limits

- Regeneration is **write-if-different**, not a blanket wipe: an unchanged
  generated file keeps its original mtime, so a downstream `cmake --build`
  can skip recompiling it — regenerating into the same output dir after a
  no-op `.harpia` edit rebuilds close to nothing (a message rename or
  removal has its old files pruned automatically). **Still never hand-edit
  generated files** — change your `.harpia` and regenerate; anything you hand
  edit gets silently overwritten (or removed, if it looks like an
  orphan) the next time you do.
- Exactly one root `.harpia` per input folder (imports go under `Include/`).
- Message ids (the `ID_*` primary key) are **caller-assigned** — set them before
  `create()`; the DB does not auto-generate them.

---

## 12. Building on Windows

Verified end to end on MSVC (Visual Studio 2022, toolset v143) + vcpkg,
covering the ZMQ server/client transport demo and the REST/JSON demo
(`HarpiaTest/app_example/consumer`, including `-DUSE_TLS=ON` and, against a live server,
`-DUSE_POSTGRES=ON`). The generator itself
(`main.py`) still only runs via Docker/Linux — this section is about the
**generated C++ project** compiling and running natively on Windows.

### One-time setup

1. Visual Studio 2022 (or Build Tools) with the "Desktop development with
   C++" workload, and a standalone CMake ≥ 3.20.
2. A fresh, standalone vcpkg clone (don't fight Visual Studio's bundled
   copy — it's in "artifacts" manifest mode and awkward to drive from plain
   CMake):
   ```
   git clone https://github.com/microsoft/vcpkg.git C:\vcpkg
   C:\vcpkg\bootstrap-vcpkg.bat
   ```

### Building the generated project (server/client ZMQ demo)

```
run_harpia.sh <input_folder> <output_folder> --no-build   # generate, from WSL/Linux
cmake -S <output_folder> -B <output_folder>\build ^
    -A x64 -DCMAKE_TOOLCHAIN_FILE=C:\vcpkg\scripts\buildsystems\vcpkg.cmake
cmake --build <output_folder>\build --config Release
```

`vcpkg.json` (copied into every generated project alongside its root
`CMakeLists.txt`) declares `protobuf`, `grpc`, `zeromq` (with its `curve` +
`sodium` features, for [§10](#10-enabling-curve-encryption-on-zmq)),
`cppzmq`, and `soci[sqlite3,postgresql]`; the CMake toolchain file drives
`vcpkg install` automatically at configure time. Expect the first configure to
take a while — gRPC in particular is slow to build from source on Windows.

### Building `HarpiaTest/app_example/consumer` (REST/JSON demo)

```
cmake -S examples\consumer -B <build_dir> -A x64 ^
    -DCMAKE_TOOLCHAIN_FILE=C:\vcpkg\scripts\buildsystems\vcpkg.cmake ^
    -DHARPIA_GEN=<output_folder>
cmake --build <build_dir> --config Release
```

Add `-DUSE_TLS=ON` the same as on Linux ([§9](#9-enabling-tls-on-restsoapgrpc))
— the demo cert step locates vcpkg's `openssl.exe` (shipped under its
`tools` feature, not on PATH by default) and its bundled `openssl.cnf`
automatically.

Add `-DUSE_POSTGRES=ON` to build against the SOCI PostgreSQL backend instead
of SQLite (build- and live-session-verified — see [§8](#8-choosing-the-database-backend)):

```
cmake -S examples\consumer -B <build_dir> -A x64 ^
    -DCMAKE_TOOLCHAIN_FILE=C:\vcpkg\scripts\buildsystems\vcpkg.cmake ^
    -DHARPIA_GEN=<output_folder_generated_with_HARPIA_DB_BACKEND=postgresql> ^
    -DUSE_POSTGRES=ON
cmake --build <build_dir> --config Release
set HARPIA_PG_CONNINFO=host=localhost port=5432 dbname=harpia user=postgres password=...
<build_dir>\Release\consumer.exe
```

`HARPIA_GEN` must point at a project generated with
`HARPIA_DB_BACKEND=postgresql` (the CRUDL SQL is dialect-specific); the demo
reads its connection string from `HARPIA_PG_CONNINFO` at runtime rather than
hardcoding credentials.

### Building the Stage 14 generated `ctest` suite

```
cmake -S <output_folder> -B <output_folder>\build ^
    -A x64 -DCMAKE_TOOLCHAIN_FILE=C:\vcpkg\scripts\buildsystems\vcpkg.cmake ^
    -DHARPIA_BUILD_TESTS=ON
cmake --build <output_folder>\build --config Release
ctest --test-dir <output_folder>\build -C Release --output-on-failure
```

Same generated project as the ZMQ demo above, reconfigured with
`-DHARPIA_BUILD_TESTS=ON` — `run_harpia.sh ... --no-build` already emits the
`tests/` tree, this just also builds it.

### Why the CMake files look the way they do

Every `if(WIN32) ... else() ...` branch in `Assets/server_template`,
`client_template`, `proto`, `HarpiaTest/app_example/consumer`'s, and the generated
`tests/`'s CMakeLists exists because vcpkg's packages export namespaced
CONFIG targets (`SOCI::SOCI`, `cppzmq`, `gRPC::grpc++`) instead of the bare
library names (`soci_core`, `zmq`) the Linux/apt path resolves by linker
search path — the Linux branch is untouched. Four source-level fixes went
into the generated *code* itself (not just build config), each with a
comment at its site explaining why:

- **protobuf version skew**: the pipeline's Docker protoc (apt's, an older
  version) bakes `.pb.h`/`.pb.cc` that won't compile against whatever much
  newer protobuf vcpkg installs. `Assets/proto/CMakeLists.txt` already
  regenerates matching code from the raw `.proto` via vcpkg's own protoc;
  the server/client/consumer/tests CMakeLists list that freshly-regenerated
  directory *ahead of* the baked one on the include path so it wins (Stage
  14's generated tests hit this same skew and needed the same fix — see
  `TestAdapter/TestAdapter.py`'s `HARPIA_TEST_PROTO_INCLUDE_DIR`).
- **`XmlAdapter`'s protobuf `Reflection` API** (`XmlAdapter/runtime/harpia_xml.h`):
  newer protobuf returns `std::string_view` from `FieldDescriptor::name()`/
  `Descriptor::name()` where older versions returned `const std::string&`;
  fixed with direct-initialization (`const std::string x(f->name())`) that
  compiles against both.
- **Crow's `HTTPMethod` enum** (`Database/templates/rest.h.tmpl`/`soap.h.tmpl`):
  Crow guards its ALL-CAPS enumerators (`GET`/`POST`/`PUT`/`DELETE`/...)
  with a single `#ifndef DELETE`, but `<windows.h>` (pulled in by Crow's own
  `#include <asio.hpp>`, well before Crow's enum) defines `DELETE` as a
  generic-access-rights macro — so Crow silently falls back to TitleCase
  members only (`Delete`/`Get`/...) and every generated
  `crow::HTTPMethod::GET` reference stops existing. Fixed by forcing
  `<windows.h>` in and undefining `DELETE` *before* `#include "crow.h"`
  (its own include guard then makes Crow/asio's later re-inclusion a no-op).
- **`tests/harpia_test_client.h`** (the REST/SOAP HTTP round-trip client the
  Stage 14 tests use — Crow ships no client): was plain POSIX sockets only;
  ported to a thin `#ifdef _WIN32` Winsock2 path alongside it (`closesocket`
  vs. `close`, `ioctlsocket`/`FIONBIO` vs. `fcntl`/`O_NONBLOCK`,
  `WSAGetLastError` vs. `errno`, `SO_RCVTIMEO` taking a `DWORD` ms value on
  Windows vs. a `timeval` on POSIX). One process-wide `WSAStartup`/
  `WSACleanup` pair via a function-local static. Links `ws2_32` on Windows
  (`#pragma comment` covers MSVC; `TestAdapter.py`'s CMake also links it
  explicitly for other toolchains).

### Known gaps on Windows

- `-DUSE_ZMQ_CURVE=ON` ([§10](#10-enabling-curve-encryption-on-zmq)):
  **verified on Windows** (MSVC 2022 + vcpkg `zeromq[curve,sodium]`,
  configure → build → a real `tcp://` CURVE client/server message
  exchange). Getting there fixed two Windows-only bugs in the root
  `CMakeLists.txt`'s CURVE branch (see `Assets/CLAUDE.md`): the keygen
  probe's `try_run` was handed the bare `libzmq` *target name* (unusable
  in `try_run`'s isolated sub-project → `LNK1104`), and the probe's
  `\r\n` stdout on Windows leaked a trailing `\r` into the parsed Z85
  secret keys (41-byte "key" → libzmq rejects it → cppzmq throws → the
  demo dies at startup with `0xC0000409`).
- **Antivirus false positives**: freshly-built, unsigned, network-listening
  executables (`server.exe` especially) can get locked or silently removed
  by a real-time antivirus's behavioral heuristics (observed with Avast).
  If a rebuild fails with `LNK1104: cannot open file ...exe` right after a
  demo run, or the `.exe` has simply vanished from the build output, add an
  exclusion for the build output folder in your antivirus and rebuild.
