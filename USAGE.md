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

Both folders may live **anywhere** on disk; the output folder is cleaned first.

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
[`examples/consumer/`](examples/consumer/) — inspect it end to end:

- [`examples/consumer/src/main.cpp`](examples/consumer/src/main.cpp) — the app.
- [`examples/consumer/CMakeLists.txt`](examples/consumer/CMakeLists.txt) — the build wiring.
- [`examples/consumer/README.md`](examples/consumer/README.md) — how to run it.

It depends only on a project you generated (via `-DHARPIA_GEN=<generated dir>`),
not on the Harpia repo:

```sh
./run_harpia.sh HarpiaTest /tmp/gen --no-build          # generate
cmake -S examples/consumer -B /tmp/cb -DHARPIA_GEN=/tmp/gen
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

---

## 7. Other ways to run it

`run_harpia.sh` is the recommended entry point. Two lower-level options:

**Interactive / scripted, inside the toolchain image:**
```sh
docker/run.sh                    # interactive shell in the harpia-build image
docker/run.sh pytest             # run Harpia's own test suite
docker/run.sh python3 main.py    # run the pipeline with the in-repo defaults
```

**Directly via `main.py`** (defaults generate the in-repo `HarpiaTest` example).
Override the paths with environment variables:

| Variable | Meaning |
|---|---|
| `HARPIA_INPUT_FILE` | path to the root `.harpia` file |
| `HARPIA_INCLUDE_FOLDER` | folder of importable modules |
| `HARPIA_OUTPUT_DIR` | where to write the generated project (cleaned first) |
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

**Worked example:** [`examples/consumer/`](examples/consumer/) demonstrates the
Crow path end to end — build it with `-DUSE_TLS=ON` to see a generated CMake
target generate a self-signed cert at configure time and serve real REST traffic
over it (see its README).

---

## 10. Notes & limits

- The output is regenerated from scratch each run — **do not hand-edit generated
  files**; change your `.harpia` and regenerate.
- Exactly one root `.harpia` per input folder (imports go under `Include/`).
- Message ids (the `ID_*` primary key) are **caller-assigned** — set them before
  `create()`; the DB does not auto-generate them.
