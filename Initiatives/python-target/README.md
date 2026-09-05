# Python Target: Language #4, Full Compliance Parity, No Carve-Outs

**Status: scoped, not started. Furthest out of the three planned language
work items** — sequenced after the entire `go-target` initiative ships
(§5), including its `tri-language-interop` epic. No epic here has task-level
files yet; see §6.

## 1. What this is

A fourth harpia generation target, after C++ (native), Java (shipped V1),
and Go (`Initiatives/go-target/`, planned). Supersedes the standing backlog
recommendation that Python be language #3 (`Initiatives/README.md`'s
Backlog section) — Go went first instead; this is that deferred work,
resequenced rather than dropped.

**Scope target: full compliance parity with the C++ target, with no
carve-outs** — unlike Go, Python needs no DDS or ZMQ-CURVE exclusion (§2).
Reuses the `LangBackend` registry `go-target`'s `lang-backend-seam` epic
builds — Python registers into it as a third/fourth entry, it does not
rebuild the seam.

## 2. Why Python needs fewer exclusions than Go

Go's two exclusions (DDS, ZMQ-CURVE/ZAP) exist because Go's *pure-Go*
ecosystem lacks mature bindings for those two C libraries. Python doesn't
have — or need — a "pure-Python" constraint: its standard bindings wrap the
exact same C libraries the C++ target already vendors/links:

- **DDS:** `cyclonedds` ships official Python bindings over the same
  vendored Cyclone DDS + DDS-Security plugins C++ uses
  (`third_party/cyclonedds{,-cxx}/`). Included, not deferred.
- **ZMQ CURVE + ZAP:** `pyzmq` wraps libzmq directly (already in the
  `harpia-build` image for the C++ target) — full CURVE and a real ZAP
  handler story, same as C++'s own `harpia_zap.h`. Included, not deferred.

**Dependency posture:** stdlib-first (`sqlite3`, `http.server`), standard
C-extension bindings where there's no stdlib option (`pyzmq`, `psycopg`,
`cyclonedds`, `grpcio`, `protobuf`). No "pure-Python" rule — it wouldn't buy
anything a normal Python deployment cares about, unlike Go's static-binary
value proposition.

One Python-specific care, not a decision: the generator itself is Python
3.10+, so generated code must land as an isolated package under `<dest>/python/`
with no module-name collision against harpia's own source tree.

## 3. Codegen and docs

Generation-time, like C++ and Go: `protoc --python_out` + `grpc_tools.protoc`
(add `grpcio-tools` to the Docker image; `protoc` itself is already present).
Docs: Sphinx + docstrings emitted per epic, Ground Rule 6 discipline, same
as Go's Doxyfile extension — no separate Python-doxygen epic (see
`Initiatives/doxygen-generation/doxygen-generation.md` and
`Initiatives/go-target/README.md` §6 for why this is a standing per-language
rule, not something to re-litigate here). Quality gate: `mypy --strict` +
`ruff`, the Python analog of Go's `go vet` + `staticcheck`.

## 4. Epics

| # | Epic | Contract |
|---|---|---|
| 1 | `py-foundation` | `HARPIA_GEN_LANG=python`; `pyproject.toml`/package layout; `_pb2.py`/`_pb2_grpc.py` at generation time; `golden_python/` baseline; Sphinx skeleton |
| 2 | `py-serialization` | JSON/XML/YAML single descriptor-reflection runtimes + unified `to_string`; phi `[REDACTED]`. Bar: XML/YAML byte-identical to the C++ target's output |
| 3 | `py-crypto-phi` | `KeyProvider` + local provider + crypto-shred + zeroization + audit sink; phi encrypt/decrypt wired into DB + serializers |
| 4 | `py-database` | DB-API 2.0 reflect bind/extract + CRUDL DAOs (reuses `Database/model.py` IR); `sqlite3` + `psycopg` dialects; public/private segregation; migration + `data_transform` |
| 5 | `py-transports-http` | REST (`http.server` + hand-rolled router) + SOAP (hand-rolled) + gRPC impls; mTLS + admin/main/guest RBAC + bearer sessions |
| 6 | `py-zmq` | PUSH/PULL + PUB/SUB via `pyzmq`; `critical` queue/CRC/flush; `stream` lifecycle; **CURVE + ZAP allowlist included** (§2 — no exclusion) |
| 7 | `py-events` | In-process `event` channels (threading + callbacks); subscribe/unsubscribe, detached dispatch, exception isolation, cache modes |
| 8 | `py-versioning` | Wire-number freeze consumption (`Message/FieldMap`); capability handshake per transport |
| 9 | `py-dds` | `dds` transport via `cyclonedds` Python bindings; QoS mapping; DDS-Security; phi-over-DDS audit. **No Go equivalent — this is the one epic Go's own initiative doesn't have (`Initiatives/go-target/README.md` §3).** |
| 10 | `py-discovery-fhir` | WS-Discovery responder; HL7 FHIR façade + worked example |
| 11 | `py-artifacts` | CycloneDX SBOM for the Python package; traceability matrix |
| 12 | `py-tests` | Generated `test_<name>.py` per message; `mypy --strict` + `ruff` gate |
| 13 | `quad-language-interop` | *(needs `go-target`'s `tri-language-interop` merged)* Extends the interop harness to add Python as a 4th peer: C++ + Java + Go + Python in one container |

## 5. Sequencing

Starts only after **all** of `go-target` (epics 0–12) ships — not just epic
0's registry. Rationale: `py-foundation` registers into the `LangBackend`
seam Go's epic 0 builds, and `quad-language-interop` extends the harness
Go's epic 12 builds; starting Python epics 1–12 earlier would just mean
redoing work once those land, since Python's own foundation/interop epics
are structurally the same shape as Go's.

## 6. Task-level planning status

**No epic here has task files yet, including `py-foundation`.** This is a
deliberate difference from `go-target` (which has `lang-backend-seam`'s
tasks written, since that epic is next-in-line). Python's own epic 1 is far
enough out — behind the entire Go initiative — that pre-authoring its task
contracts now would likely go stale: the exact `LangBackend` registry
interface, the reflection-runtime pattern, and the interop harness shape are
all things Go's own build-out will concretize. Re-plan `py-foundation`'s
tasks when `go-target` is close to shipping, not before.

## 7. Non-goals

- A "pure-Python" dependency rule (§2 — not meaningful here).
- Performance/throughput benchmarking (matches the other two initiatives'
  own non-goals).
- Bringing C++ or Java up to whatever Python ends up doing differently
  (each target's own scope stands on its own, per `go-target/README.md` §4's
  same principle for Java).
