# Go Target: Language #4, Full Compliance Parity Except DDS and ZMQ-CURVE

**Status: scoped, not started. Resequenced 2026-10-03 behind
`python-target`** (Python became language #3 at another project's request).
Go depends on python-target's epic 0 (`lang-backend-seam`, moved there from
this initiative on 2026-10-03) and its interop epic extends python-target's
three-language harness. Still also after `doxygen-generation`'s
`doc-comment-coverage`. Planned 2026-09-02/03; not yet branched.

## 1. What this is

A fourth harpia generation target, after C++ (native), Java (fully shipped,
V1, `Initiatives/multi-language-targets/` — removed on completion, behavior
now lives in the `Java*`/`GradleAdapter` module `CLAUDE.md` files and
`README.md`'s "Additional language targets"). Chosen ahead of the standing
backlog recommendation (`Initiatives/README.md`'s Backlog section named
Python as the natural #3, deferred when Java's Android-fleet need arrived) —
a deliberate reprioritization, no single external consumer driving it this
time (general-purpose third target).

**Scope target: full compliance parity with the C++ target** — phi
encryption+audit+redaction, `critical` delivery, mTLS/RBAC/bearer sessions,
in-process events, `stream` lifecycle, schema migration + `data_transform`,
public/private DB segregation, wire-number versioning + capability handshake,
WS-Discovery, FHIR façade, SBOM/traceability — **except** two items excluded
for a concrete technical reason, not oversight (§3).

## 2. Dependency posture: pure Go

Every dependency is pure Go, no cgo: `modernc.org/sqlite`, `jackc/pgx`
(Postgres), `go-zeromq/zmq4`. Rationale: keeps the "single static binary,
trivial cross-compile" value proposition intact for every Go consumer, and
keeps the Docker image simple (no libzmq/libsqlite3 linkage story to
maintain for Go specifically — C++ already needs those for its own reasons,
Go doesn't need to share that surface).

## 3. What's excluded from parity, and why

- **DDS transport.** No pure-Go implementation of OMG DDS-Security exists
  (the C++ target's DDS-Security is Cyclone DDS's C plugins — auth/
  access-control/crypto — driven by signed governance/permissions XML and a
  PKI; nothing comparable exists in pure Go today). Decision: **defer and
  disclose**, not a silent gap — DDS is not harpia's core business to
  reimplement from scratch in Go; revisit if/when a pure-Go DDS-Security
  stack matures enough to trust. No epic covers it in this initiative.
- **ZMQ CURVE encryption + ZAP client-key allowlist.** The pure-Go ZMQ
  binding (`go-zeromq/zmq4`) has incomplete CURVE support and no real ZAP
  handler; the complete implementation (`pebbe/zmq4`) requires cgo + libzmq,
  which would break the pure-Go rule for this one transport. Decision:
  **plaintext ZMQ only for Go v1**, disclosed in `go-zmq`'s own docs and in
  every generated Go ZMQ header's top comment, same as the C++/Java targets
  disclose their own scope cuts (e.g. Java's DB layer skipping embed/FK/map
  columns, `JavaDatabase/CLAUDE.md`). A CURVE/ZAP follow-up epic is a
  legitimate later addition if a pure-Go CURVE implementation matures, or if
  the cgo trade-off becomes acceptable for that one transport.

Everything else has a solid pure-Go story: `database/sql` + `modernc.org/sqlite`
+ `jackc/pgx`; `google.golang.org/protobuf` (incl. `protoreflect` for the
single-runtime reflection strategy Java already validated); `net/http` for
REST; `google.golang.org/grpc`.

## 4. The language-backend seam (owned by python-target since 2026-10-03)

Java's own docs (`GradleAdapter/CLAUDE.md`) explicitly deferred designing a
real language-plugin abstraction "until a second language exists". The
`LangBackend` registry (`main.py` dispatches through it for every target;
Java retrofitted with **zero output change**) was planned here as epic 0,
then **moved to `Initiatives/python-target/epics/lang-backend-seam/`** when
Python was resequenced first. Go registers into it in `go-foundation`; it
does not rebuild it.

## 5. Codegen timing: generation-time, unlike Java

Java chose build-time codegen (`protobuf-gradle-plugin` runs `protoc` inside
the *consumer's* `gradle build`) because the Gradle ecosystem already expects
that. Go has no equivalent dominant build-tool plugin, so Go leans back
toward **generation-time codegen like C++**: harpia itself runs
`protoc-gen-go` + `protoc-gen-go-grpc` (both tiny pure-Go binaries) and
commits the resulting `.pb.go` under `<dest>/go/`. Docker image gains: Go
toolchain, `protoc-gen-go`, `protoc-gen-go-grpc`.

## 6. Doxygen / docs

Per Ground Rule 6 (`Initiatives/doxygen-generation/doxygen-generation.md`),
each Go epic emits its own doc-comments for the Go templates it touches, in
the same sitting — **not** a separate Go-doxygen epic, and not folded into
the existing `doc-comment-coverage` epic (that one stays scoped to the
current C++ backlog only). `go-foundation` (epic 1) extends the Doxyfile/
mainpage plumbing to cover the Go tree as one task.

## 7. Epics

| # | Epic | Contract |
|---|---|---|
| 0 | ~~`lang-backend-seam`~~ | **Moved to `python-target` (epic 0) 2026-10-03.** Prerequisite of `go-foundation`. |
| 1 | `go-foundation` | `HARPIA_GEN_LANG=go`; `go.mod`/package layout; `.proto`→`.pb.go`+gRPC stubs at generation time; `golden_go/` baseline; Doxyfile covers the Go tree |
| 2 | `go-serialization` | JSON/XML/YAML single `protoreflect`-based runtimes; unified `ToString`; phi `[REDACTED]`. Bar: XML/YAML byte-identical to the C++ target's output (JSON is portable for free via protobuf canonical JSON) |
| 3 | `go-crypto-phi` | `KeyProvider` + local provider + crypto-shred + zeroization + audit sink (ports `Crypto/runtime/*.h`); phi encrypt-on-write/decrypt-on-read wired into DB + serializers |
| 4 | `go-database` | `database/sql` reflect bind/extract runtime + per-message CRUDL DAOs (reuses `Database/model.py` IR unmodified); sqlite + postgres dialects; public/private DB segregation registry; migration + `data_transform` |
| 5 | `go-transports-http` | REST (`net/http`) + SOAP (hand-rolled) + gRPC service impls; mTLS + admin/main/guest RBAC + bearer sessions (ports `harpia_rbac.h`/`harpia_session.h` logic) |
| 6 | `go-zmq` | PUSH/PULL + PUB/SUB core over `go-zeromq/zmq4`; `critical` bounded-queue/CRC/flush runtime; `stream` lifecycle. **Plaintext only** — see §3 |
| 7 | `go-events` | In-process `event` channels via Go channels + goroutines; subscribe/unsubscribe, detached dispatch, panic isolation, cache modes — ports `test_events_callbacks.py`'s bar |
| 8 | `go-versioning` | Wire-number freeze consumption (reuses `Message/FieldMap`, language-agnostic already); capability handshake per transport |
| 9 | `go-discovery-fhir` | WS-Discovery responder; HL7 FHIR façade + worked example |
| 10 | `go-artifacts` | CycloneDX SBOM for the Go module; traceability matrix |
| 11 | `go-tests` | Generated `*_test.go` per message (field access, JSON/XML/YAML round-trip, DB CRUDL round-trip); `go vet` + `staticcheck` gate |
| 12 | `quad-language-interop` | *(needs 1–8 merged + python-target's `tri-language-interop`)* Adds Go as the 4th peer to python-target's C++/Java/Python harness: ZMQ fan-out/load-balance (plaintext only, §3), shared-DB cross-read/write, gRPC/REST cross-calls, JSON/XML/YAML byte-parity — one `.harpia`, one frozen `schema_registry/` |

**No epic here has task files** (epic 0's moved to python-target with the
epic). Epics 1–12 get their task-level breakdown when picked up, per the
"don't let documentation sprawl" guidance in the `harpia-workflow` skill —
python-target's task files (written 2026-10-03, same epic shapes) are the
template to adapt, minus DDS and CURVE/ZAP.

## 8. Sequencing

```
python-target (all, incl. its epic 0 lang-backend-seam + tri-language-interop)
doc-comment-coverage (doxygen, independent)
        │
        ▼
go-foundation … go-tests (epics 1–11, roughly the table order above;
                          4/5/6/7 have no hard ordering between them)
        ▼
quad-language-interop (epic 12)
```

## 9. Non-goals

- Bringing the Java target up to this initiative's compliance-parity scope
  (separate initiative if ever wanted — see §4).
- DDS and ZMQ-CURVE/ZAP for Go (§3).
- Performance/throughput benchmarking (matches
  `transport-multipeer-coverage`'s own non-goals).
- Android/mobile consumption of the Go target (Java's Android story was a
  concrete need; nothing analogous exists for Go here).
