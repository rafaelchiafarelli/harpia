# python-target — epics

14 epics (0–13), 54 tasks. See `../README.md` §4 for the contract table and
§6 for the decisions recorded on 2026-10-03.

## Order / dependency graph

```
lang-backend-seam (0)
        │
        ▼
py-foundation (1)  ── toolchain image, python backend, layout, golden, gate, AuditSink
        │
        ├──► py-serialization (2) ─────────────┐
        ├──► py-database (4) ──────────────────┤
        │        (task 6 dbio needs 2)          │
        ├──► py-crypto-phi (3)  tasks 1–3 need only 1; task 4 needs 4 (+2 for redaction already shipped)
        ├──► py-transports-http (5)  (needs 2 + 4)
        ├──► py-zmq (6)
        ├──► py-events (7)  task 1 needs only 1; task 2 needs 4 task 2a (+ 3 task 4 for phi)
        ├──► py-versioning (8)  (needs 5 + 6)
        └──► py-dds (9)
                │
                ▼
py-discovery (10)        (needs 5's SOAP endpoint)
py-artifacts (11)        (do late — enumerates the others' files/deps)
py-tests (12)            (needs 2, 4, 5)
        │
        ▼
tri-language-interop (13)   (needs 1–9 merged)
```

Within 3/5/6/7/9 there is no hard ordering. Pick whichever is clearest once
1/2/4 exist. Inside each epic, tasks run in numeric order unless the task
file says otherwise.

## Cross-epic gate (initiative done)

- Every epic's DoD below holds.
- `tri-language-interop` (13) passes in the full suite.
- A real generated project (`HarpiaTest/test.harpia` +
  `HARPIA_GEN_LANG=python`) passes its own generated test suite, `mypy
  --strict` and `ruff`, with zero changes to `golden/` (C++) or
  `golden_java/`.

## Definition of done (every epic)

This is the source of truth for both language initiatives. `go-target`'s
`epics/README.md` points here, substituting `golden_go/` and its own lint
gate.

- The epic's contract (one line in `../README.md` §4) is delivered **and
  demonstrated by a real generated project**, not only unit tests of an
  adapter in isolation.
- Full suite green in Docker (`Docker/run.sh pytest UnitTests/`), including
  the C++ and Java targets. Watch `golden/`, `golden_java/` and
  `golden_python/` on every epic: a Python change that moves a C++/Java
  golden byte is a bug unless the task says otherwise.
- `mypy --strict` + `ruff` green on the generated `<dest>/python/` tree
  (gate from `py-foundation` task 3).
- Deliberately reduced scope is disclosed in the epic's own module
  `CLAUDE.md` and in docstrings, never silent.
- Ground Rule 6: docstrings on every consumer-facing template/runtime the
  epic touches, rendered by the Sphinx skeleton, in the same sitting.
- **Wire and file-format compatibility with C++ is a contract, not a nicety.**
  Wherever C++ defines a format, Python produces and accepts it byte-for-byte
  unless the task says otherwise. That covers: serialized protobuf frames,
  the `enc:v1:` column framing, the `LocalKeyProvider` store, session
  tokens, the ZAP allowlist file, the DDS frame type, XML/YAML text and the
  SQL schema. Each task names its cross-check.

## Python-specific conventions (apply to every epic)

- **Layout** (`py-foundation` task 2):
  - `<dest>/python/` is one installable project (`pyproject.toml`).
  - `harpia_runtime/` holds hand-written modules copied verbatim (the
    `com.harpia.runtime` / `harpia_xml.h` pattern).
  - `harpia_generated/` holds generated per-message modules.
- **Per-message module names carry the hash:**
  `harpia_generated/<kind>/<name>_<hash>_<kind>.py`. That way
  `Util.util.prune_stale_outputs` (`_NAME_HASH_RE`) reaps a removed message's
  files for free. Java's `<name>_dao.java` lacks the hash and is not pruned;
  don't repeat that.
- **No accessor-name guessing.** Python protobuf attributes are the exact
  `.proto` field names, so `getattr(msg, field.name)` /
  `msg.DESCRIPTOR.fields_by_name` is exact. The camelCase hazard that forced
  reflection in Java doesn't exist here. Reflection is still preferred for
  runtimes that must be message-agnostic.
- **Python floor 3.10** (match statement allowed; no 3.11+ features). The
  image runs 3.12.
- **Synchronous API + threads**, mirroring C++/Java (`../README.md` §7).
- **Python's analogue of "header copied verbatim":** a `.py` file under the
  adapter's `runtime/` dir, copied with `copy_if_different`.

## Epic summaries

### 0. `lang-backend-seam`
Receives: nothing. Gives: `get_lang_backend(name)` + `cpp`/`java` backends,
`main.py` dispatching through it, goldens byte-identical. Tasks 1–3
(written 2026-09-03 under `go-target`, moved here 2026-10-03).

### 1. `py-foundation`
Receives: 0. Gives:
- the Python toolchain in the image (1);
- the `python` backend + `<dest>/python/` layout + protoc codegen +
  `golden_python/` (2);
- Sphinx + `mypy --strict` + `ruff` gate (3);
- `harpia_runtime.compliance.audit_sink` (4).

Tasks 1–4.

### 2. `py-serialization`
Receives: 1. Gives:
- JSON (1), XML (2), YAML (3) runtimes;
- the `to_string` façade + phi redaction + audited opt-out (4).

XML/YAML byte-identical to C++. Tasks 1–4.

### 3. `py-crypto-phi`
Receives: 1 (tasks 1–3), 4 (task 4). Gives:
- `KeyProvider` + in-memory provider + shred + zeroize + audit (1);
- `LocalKeyProvider` + KMS seam (2);
- `enc:v1:` encrypted-column helpers, C++-compatible (3);
- phi DAOs that encrypt/decrypt/audit (4).

Tasks 1–4.

### 4. `py-database`
Receives: 1 (2 for task 6). Gives:
- bind/extract runtime (1);
- DAOs: scalar + pagination (2a), embed + FK (2b), map/repeated child
  tables (2c);
- Postgres (3);
- public/private registry (4);
- migrations, main table (5a) and child tables (5b);
- DB↔JSON/XML io (6).

Tasks 1, 2a–2c, 3, 4, 5a, 5b, 6.

### 5. `py-transports-http`
Receives: 2, 4. Gives:
- connection pool (1);
- REST (2), SOAP (3), gRPC (4) with the flat gate;
- fail-safe mTLS server + client helpers (5);
- RBAC + per-message `protected`/`open` (6);
- bearer sessions, C++-compatible tokens (7).

Tasks 1–7.

### 6. `py-zmq`
Receives: 1. Gives:
- core PUSH/PULL/PUB/SUB + origin ids (1);
- CURVE + ZAP allowlist (2);
- `critical` delivery runtime + sender (3);
- `stream` lifecycle (4).

Tasks 1–4.

### 7. `py-events`
Receives: 1 (task 1), 4 + 3 (task 2). Gives:
- `EventChannel` runtime + per-message accessors (1);
- DAO OnChange publish + `phi_event_onchange` (2).

Tasks 1–2.

### 8. `py-versioning`
Receives: 5, 6. Gives:
- shared dispatcher + gRPC handshake (1);
- HTTP + ZMQ handshake (2);
- wire-number freeze proof for Python peers (3).

Tasks 1–3.

### 9. `py-dds`
Receives: 1 (task 4 also needs 3's audit). Gives:
- DDS pub/sub over `harpia_dds::Frame` (1);
- QoS mapping (2);
- DDS-Security (3);
- phi-over-DDS audit (4).

Tasks 1–4.

### 10. `py-discovery`
Receives: 5 task 3. Gives: a WS-Discovery responder for the Python SOAP
endpoint. Task 1.

### 11. `py-artifacts`
Receives: everything it enumerates. Gives:
- Python components in `bom.json` (1);
- Python rows/evidence in the traceability matrix (2).

Tasks 1–2.

### 12. `py-tests`
Receives: 2, 4, 5. Gives:
- generated per-message unit tests (1);
- access/REST/SOAP bodies + app-level suite (2).

Tasks 1–2.

### 13. `tri-language-interop`
Receives: 1–9. Gives:
- ZMQ 3-language fan-out/load-balance (1);
- shared-DB cross read/write (2);
- gRPC/REST cross-calls, flat + hardened (3);
- serialization byte-parity (4);
- DDS C++↔Python (5).

Tasks 1–5.
