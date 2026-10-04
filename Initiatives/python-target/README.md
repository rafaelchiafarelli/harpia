# Python Target: Language #3, Full Compliance Parity, No Carve-Outs

**Status: planned, not started — every epic has task files (2026-10-03).**
Resequenced ahead of `go-target` on 2026-10-03: another project asked for a
Python harpia target, so Python becomes language #3 and Go moves to #4.
Implementation is sequenced after `multi-system-reference` finishes in the
clone it lives in (that initiative is mid-flight; see §5).

## 1. What this is

A new harpia generation target alongside C++ (native) and Java (shipped V1).
It supersedes the old backlog item "Python as language #3"
(`Initiatives/README.md`'s Backlog section). That item was first displaced by
Go, and is now restored to #3.

**Scope target: full compliance parity with the C++ target, with no
carve-outs.** Unlike Go, Python needs no DDS or ZMQ-CURVE exclusion (§2).
That means:

- phi encryption, audit and redaction;
- `critical` delivery;
- mTLS, RBAC and bearer sessions;
- in-process events and the `stream` lifecycle;
- migration plus `data_transform`;
- public/private DB segregation;
- capability handshake;
- DDS and DDS-Security;
- WS-Discovery;
- SBOM and traceability.

Python goes **beyond** the Java target in places (full DB column coverage, a
server-side transport stack, RBAC and sessions on the server). Java's scope
is not raised to match. That would be its own initiative.

## 2. Why Python needs fewer exclusions than Go

Go's two exclusions (DDS, ZMQ-CURVE/ZAP) exist because Go's *pure-Go*
ecosystem lacks mature bindings for those two C libraries. Python has no
"pure-Python" constraint. Its standard bindings wrap the exact C libraries
the C++ target already uses:

- **DDS:** `cyclonedds` (Python) builds against the same vendored Cyclone
  DDS 0.10.5 + DDS-Security plugins that C++ uses
  (`third_party/cyclonedds/`). Included, not deferred.
- **ZMQ CURVE + ZAP:** `pyzmq` wraps libzmq directly; libzmq is already in
  the `harpia-build` image. It gets full CURVE plus a real ZAP handler, the
  same as C++'s `harpia_zap.h`. Included, not deferred.

**Dependency posture (decided 2026-10-03):** stdlib first (`sqlite3`,
`http.server`, `ssl`, `hmac`, `xml.etree`, `zlib`). Where no stdlib option
exists, use the standard C-extension bindings (`protobuf`, `grpcio`, `pyzmq`,
`psycopg`, `cyclonedds`).

In the Docker image, packages come **from apt first**: the Ubuntu
`python3-*` packages match the image's `protoc` 3.21.12. **Pinned pip** is
used only for what apt doesn't carry (`ruff`, `cyclonedds==0.10.5`,
`mypy-protobuf`). See `py-foundation` task 1.

## 3. Codegen and docs

**Codegen happens at generation time, like C++** (not build time like Java):

- `protoc --python_out` + `--pyi_out`/`mypy-protobuf` for messages;
- `grpc_tools.protoc --grpc_python_out` for services.

The output is committed under `<dest>/python/`.

**Docs:** Sphinx + docstrings, emitted per epic under Ground Rule 6.
There is no separate Python-docs epic. See
`Initiatives/doxygen-generation/doxygen-generation.md` for why this is a
standing per-language rule.

**Quality gate:** `mypy --strict` + `ruff` over the generated tree. This is
the Python analog of Go's `go vet` + `staticcheck`. It is set up once in
`py-foundation` and every epic keeps it green (epics/README.md DoD).

## 4. Epics

| # | Epic | Contract |
|---|---|---|
| 0 | `lang-backend-seam` | `LangBackend` registry; `main.py` dispatch; Java retrofit, wiring only. Moved here from `go-target` 2026-10-03. |
| 1 | `py-foundation` | Python toolchain in the image; `HARPIA_GEN_LANG=python` backend; `pyproject.toml`/package layout; `_pb2.py`/`_pb2_grpc.py` at generation time; `golden_python/` baseline; Sphinx + `mypy --strict` + `ruff` gate; the `AuditSink` runtime every later epic records into |
| 2 | `py-serialization` | JSON/XML/YAML descriptor-reflection runtimes + unified `to_string`; phi `[REDACTED]` + audited opt-out. Bar: XML/YAML byte-identical to C++, JSON cross-parse-equal |
| 3 | `py-crypto-phi` | `KeyProvider` (in-memory, local, KMS seam) + crypto-shred + best-effort zeroization + audit; `enc:v1:` encrypted-column framing byte-compatible with C++; phi encrypt/decrypt + audit wired into the DAOs |
| 4 | `py-database` | DB-API bind/extract + CRUDL DAOs over `Database/model.py`'s IR (**full** column coverage: embed, FK, map, repeated, repeated-FK, repeated-composed, pagination); `sqlite3` + `psycopg`; public/private registry; migration + `data_transform`; DB↔JSON/XML io |
| 5 | `py-transports-http` | Connection pool; REST (`http.server` + hand-rolled router), SOAP (hand-rolled), gRPC servicers + bring-ups; mTLS (fail-safe) + admin/main/guest RBAC + bearer sessions, per-message `protected`/`open` |
| 6 | `py-zmq` | PUSH/PULL + PUB/SUB via `pyzmq`; CURVE + ZAP allowlist; `critical` queue/CRC/flush; `stream` lifecycle |
| 7 | `py-events` | In-process `event` channels (threads + callbacks): subscribe/unsubscribe, detached dispatch, exception isolation, cache modes, phi OnChange audit; DAO OnChange wiring |
| 8 | `py-versioning` | Capability handshake (gRPC/HTTP/ZMQ) + shared dispatcher; proof that wire-number freezing (`Message/FieldMap`) holds for Python peers |
| 9 | `py-dds` | `dds` transport via `cyclonedds` Python (same `harpia_dds::Frame` topic type); QoS mapping; DDS-Security (fail-safe); phi-over-DDS audit |
| 10 | `py-discovery` | WS-Discovery responder advertising the Python SOAP endpoint. **No FHIR façade** (§6) |
| 11 | `py-artifacts` | Python components in the CycloneDX SBOM; Python mechanisms/evidence in the traceability matrix |
| 12 | `py-tests` | Generated `test_<name>_<hash>.py` per table message + app-level suite (parity with `TestAdapter`'s bodies) |
| 13 | `tri-language-interop` | C++ + Java + Python in one container: ZMQ fan-out/load-balance, shared DB, gRPC/REST cross-calls (flat + hardened), serialization byte-parity, DDS C++↔Python |

Task files: `epics/<epic>/tasks/`. Order and cross-epic gates:
`epics/README.md`.

## 5. Sequencing

- Epic 0 (`lang-backend-seam`) is first: it is a pure refactor and the
  registry Python plugs into.
- Epics 1–12 follow `epics/README.md`'s graph.
- Epic 13 needs 1–9 merged.
- `go-target` now depends on this initiative's epic 0 (the seam). Its
  interop epic becomes "add Go as the 4th peer" to the harness built in
  epic 13 here.

**Clone / branch note:** the working clone currently carries the
`multi-system-reference` chain (`features → multi-system-reference → epics →
…`). Per the `harpia-workflow` skill, a clone holds one initiative chain at a
time. So python-target is implemented either in a separate clone or after
multi-system-reference's chain has merged up. That is Rafael's call when
work starts.

## 6. Decisions recorded (Rafael, 2026-10-03)

- **Python ahead of Go.** Driven by an external project's request.
- **Seam ownership:** `lang-backend-seam` moved from `go-target` into this
  initiative as epic 0.
- **Interop:** a three-language C++/Java/Python harness (epic 13), not a
  four-language one blocked on Go.
- **No FHIR façade.** The C++ target has none: FHIR exists only as the
  hand-mapped worked example in `UnitTests/fhir_worked_example/`. A façade
  would be a new feature for every target and belongs in its own
  initiative. The discovery epic is WS-Discovery only.
- **Toolchain:** apt first, pinned pip for the rest (§2).

Open decisions that a task must bring to Rafael before implementing are
written in that task file under **Decision needed**. They are never settled
silently.

## 7. Non-goals

- A "pure-Python" dependency rule (§2).
- Performance/throughput benchmarking.
- A FHIR façade (§6).
- Bringing C++ or Java up to whatever Python does differently. Each target's
  scope stands on its own.
- asyncio variants of the generated APIs. The generated surface is
  synchronous plus threads, mirroring the C++/Java shape. An async layer
  would be its own initiative.
