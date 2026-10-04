# multi-system-reference — epics

## Order

```
java-hardened-client (1)      db-concurrency (2)
            \                    /
             ▼                  ▼
            reference-system (3)
             /                  \
            ▼                    ▼
   load-harness (4)     windows-verification (5, Windows session)
```

Epics 1 and 2 are independent of each other and can run in parallel clones.
Epic 3 tasks 1–2 (`provision-san-and-bulk`, `schema-and-profile`) depend on
nothing and can start alongside 1 and 2. Epic 3 task 3 (`station`) needs
epic 2 tasks 1a + 1b; task 5 (`handheld`) needs all of epic 1.

## Cross-epic gate (initiative done)

- The Linux/Docker end-to-end gate (epic 3 task 6) passes in the full suite.
- The smoke-at-scale gate (epic 4 task 4) passes.
- Epic 5 is reported done by the Windows session. Until then the initiative
  stays open, and that is stated in the index, not glossed over.

## Epic summaries

### 1. `java-hardened-client`
Receives: nothing. Gives: a generated Java runtime that opens an mTLS gRPC
channel, obtains and presents a harpia session token, and connects a CURVE
ZMQ socket that a C++ ZAP allowlist accepts. Proven on the JVM and on an
Android emulator against **C++ servers**. Tasks 1–4 written.

### 2. `db-concurrency`
Receives: nothing. Gives: `GrpcServer` / `HttpServer` constructors that take
a `soci::connection_pool&` (the old `soci::session&` constructors kept,
additive). Every call borrows exactly one connection through a generated RAII
helper, with a borrow timeout (`RESOURCE_EXHAUSTED`), reconnect on borrow,
rollback on return, and guaranteed give-back (1a). SQLite `:memory:` is
refused with a pool, file SQLite gets WAL + busy timeout, and the other
server-shared state (audit sink, key provider, sessions, RBAC map) is
audited for thread safety (1b). REST/SOAP get the same helper (2).
Tasks 1a, 1b, 2 written; task 1 was split into 1a/1b on 2026-09-26 after
Rafael reviewed the pool's weaknesses.

### 3. `reference-system`
Receives: epic 2 tasks 1a + 1b (from task 3), epic 1 (for task 5). Gives:
`HarpiaTest/app_example/multi_system/` (schema, PKI script, `station`,
`edge`, `handheld-core` + Android app + JVM CLI, README) and a pytest
end-to-end gate. Tasks 1–6 written.

### 4. `load-harness`
Receives: epic 3. Gives: `--load` mode in `edge` and `handheld-core`, a
cross-platform spawner, a report aggregator, and a Docker smoke gate.
Tasks 1–4 written.

### 5. `windows-verification`
Receives: epic 3 (and ideally 4). Gives: `station` built with MSVC + vcpkg,
running hardened + pooled against PostgreSQL on Windows, reached by `edge`
on real Linux and `handheld` on a real Android device. One task, written,
**executed by the Windows session, not the Linux one.**
