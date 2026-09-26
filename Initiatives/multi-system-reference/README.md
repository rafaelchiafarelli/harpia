# Multi-system reference: Android (Java) + Linux (C++) + Windows DB server

**Status: scoped, not started.** Planned 2026-09-26. Sequenced **next**, ahead
of `doxygen-generation`'s `doc-comment-coverage` and `go-target`, per Rafael
(2026-09-26): development on a real multi-program product is about to start
and this is the missing proof.

## 1. Why

Every harpia example so far is one program, or one language pair on one
machine. Nothing shows the problem a real harpia user has: **several
programs, in several languages, on several operating systems, all generated
from one `.harpia` and talking to each other over hardened transports**, and
nothing shows that the setup survives **hundreds of concurrent clients**.

Things that are unproven today (checked 2026-09-26, not assumed):

- **Android has never talked to a real server over the network.** The
  Android gRPC test (`HarpiaTest/app_example/android_consumer`) only builds a
  client from the generated code and never makes a call. The ZMQ test is a
  round trip inside one emulator.
- **The Java target has no hardened *client*.** mTLS, RBAC and bearer
  sessions exist only on the C++ servers (`Database/runtime/harpia_grpc_mtls.h`
  has a C++ `channel_credentials()`; there is no Java equivalent). Java has
  ZMQ CURVE (`JavaZmqAdapter`) but it has never been tested against a C++
  server that enforces the ZAP allowlist.
- **The generated servers share one DB connection across threads.**
  `GrpcServer(::soci::session& db, …)` (`Database/templates/grpc_server_bringup.h.tmpl`)
  hands that one session to every service. gRPC calls services from a thread
  pool and a `soci::session` is not thread-safe, so concurrent clients race
  on it. Harmless in the 1-client tests, but it breaks the load scenario.
- **The dev PKI can't address a server on another machine.**
  `Assets/cmake/mtls_provision.sh` hard-codes the server SAN to
  `<server_CN>, localhost, 127.0.0.1`, and issues client identities one
  argument at a time. That doesn't work for a Windows host reached by LAN
  IP/hostname, or for hundreds of client identities.

## 2. The reference system

Three programs generated from **one** `.harpia` schema and one hardened
compliance profile:

| Program | Language / OS | Role | Talks to |
|---|---|---|---|
| `station` | C++, **Windows** (also builds on Linux for CI) | The only DB owner (PostgreSQL). Hosts the generated `GrpcServer`: mTLS required, RBAC, sessions. | serves `edge` + `handheld` |
| `edge` | C++, **Linux**, no DB | Writes readings to `station` over gRPC. Publishes a live stream over ZMQ PUB (CURVE + ZAP allowlist). | → `station` (gRPC), → `handheld` (ZMQ) |
| `handheld` | Java, **Android** | Subscribes to `edge`'s live stream. Writes/reads records on `station` over gRPC. | → `station` (gRPC), ← `edge` (ZMQ) |

Transports (decided 2026-09-26): **gRPC for everything that touches the
DB server, ZMQ PUB/SUB for the Linux→Android live stream.**
Security (decided 2026-09-26): **hardened from day one.** Every gRPC link
uses mTLS + RBAC + a bearer session, and the ZMQ link uses CURVE + the ZAP
allowlist. That is why `java-hardened-client` is a prerequisite epic and not
something deferred.

## 3. The load capability

Rafael will run the real stress test elsewhere. This initiative provides the
**capability**: a spawner that starts hundreds of `edge`-type and
`handheld`-type clients against one `station`, each with its own identity,
and collects per-operation results into one report.

"Hundreds of Android" (decided 2026-09-26): the `handheld` logic lives in a
**plain-Java `handheld-core` module**. The Android app is a thin shell over it,
and a headless JVM launcher runs it hundreds of times. A handful of real
emulators run alongside for on-device realism. Hundreds of emulators is not
a goal (about 2 GB RAM and one core each).

## 4. Epics

See [epics/README.md](epics/README.md) for order and dependencies.

| # | Epic | What it delivers |
|---|---|---|
| 1 | `java-hardened-client` | Java/Android gRPC client over mTLS + sessions, Java CURVE client vs C++ ZAP, all proven on-device |
| 2 | `db-concurrency` | Generated servers draw from a `soci::connection_pool` instead of sharing one session |
| 3 | `reference-system` | The schema, PKI, and the three programs; an end-to-end gate on Linux/Docker |
| 4 | `load-harness` | Load mode in the clients, a spawner, a report aggregator, a smoke-at-scale gate |
| 5 | `windows-verification` | `station` built and run on real Windows, reached from real Linux + Android; **delegated to the Windows session** |

## 5. Non-goals

- Benchmark numbers. The harness is the deliverable; the numbers come from
  Rafael's own runs on real hardware.
- Hundreds of real emulators or a device farm integration.
- Production PKI or key distribution. The dev PKI is extended, not replaced.
- REST/SOAP clients on Java/Android. gRPC is the chosen client transport.
  REST/SOAP servers still get the connection pool (epic 2 task 2) so they
  don't keep the same race.
- Java feature parity beyond the hardened *client* (Java servers stay
  unhardened — same non-goal as `go-target` §9).
