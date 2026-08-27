# NEXT_SESSION — sensitive-data implementation (`phi` + `critical`)

Handoff for the session continuing the medical-device sensitive-data work.
Branch: **`feature/sensitive-data-implementation`** (off `dev`, pushed).

The master plan for this effort is
**[`Initiatives/medical_devices/sensitive-data-implementation-roadmap.md`](Initiatives/medical_devices/sensitive-data-implementation-roadmap.md)** —
read it first. It sequences the `harpia_medical_master_plan.md` §5 tracks and
its "Execution log" section records the actual order taken. Foundation F1–F6
is done (plumbing stubs, merged to `dev`, thread removed — see
`Initiatives/medical_devices/epics/handoff-document.md`).

**Definition of done for the whole effort** (roadmap + confirmed with the
owner): two headline integration tests — one that sends+receives a `critical`
message (delivery machinery engages), one that sends+receives a `phi` field
(redaction AND envelope encryption round-trip). Plus, per master-plan §4: unit
tests for every new construct, `UnitTests/test_golden.py` regenerated + diff
reviewed, and a traceability note into `ComplianceReport/` for phi-adjacent
work.

---

## What this session did

### Phase 1a — `critical` message-type modifier  (commit `b433dd5`, full Docker suite 211 passed)

The criticality axis of the design-rules doc §0 — message-type-level, never
per-field, independent of `phi`. Landed as an **AST flag only** (mirrors how
Foundation F2 landed `phi`); no behaviour yet.

- `LexicalAnalizer/LexicalAnalyzer.py` — `('CRITICAL', r'critical ')`, a
  keyword-only trailing-space token in the same slot as `EVENT`/`STREAM`.
- `Message/Message.py` — `Message.is_critical` bool, set when `CRITICAL`
  appears in `access_modifiers`. Composes with any transport kind
  (`critical event message …`), order-independent. **Also fixed a latent
  bug**: a leading message-type modifier on the *first* message in a token
  stream was silently dropped (`tokens[j+1:j]` empty slice) — now
  `modStart = 0 if curNewLine is None else curNewLine+1`.
- `UnitTests/run_phi_check.py` — now also reports per-message
  `is_critical`/`is_enum` in its JSON (`messages: [...]` key).
- `UnitTests/test_critical_modifier.py` — 12 tests.
- Fixture: `critical event message alarm_event` added to
  `HarpiaTest/Include/file3.harpia` (carries a `phi` field too — the axes are
  independent, Rule 0). Goldens regenerated: one new message, **zero drift on
  existing messages**, root `HASH` unchanged (only `file3.harpia`'s own md5
  changed, and only the root file's text feeds the pinned HASH — see
  `HarpiaTest/CLAUDE.md`).

### Phase 3a — delivery-guarantee runtime  (this commit; host-green, Docker suite was running at commit time)

Hand-written transport-/payload-agnostic C++, same posture as
`Capability/runtime/harpia_capability_dispatch.h` (copied verbatim into
generated output later — Phase 3b's job; nothing copies it yet).

- **`Compliance/runtime/harpia_delivery.h`** — namespace `harpia::delivery`:
  - `Envelope{seq, crc, delivery_timestamp_ms, payload}` — `Envelope::stamp()`
    computes a self-contained CRC-32 (IEEE, no zlib) at origin (Rule 3);
    `crc_ok()` verifies at a boundary.
  - `check_on_arrival(env, expected_seq)` → `Arrival{Ok, CrcMismatch, SeqGap,
    SeqRegressed}` (crc checked first, then monotonic-seq gap detection).
  - `BoundedQueue(capacity, AuditSink& = default_audit_sink(), subject)`
    (Rule 4a, for `critical` types) — FIFO, fixed capacity, `push()` →
    `PushOutcome{Accepted, RotatedOldest}`; on overflow drops the OLDEST,
    bumps `rotations()`, exposes `last_rotated_seq()`, and calls
    `audit.record("queue_rotated", subject, "dropped_seq=N")` — never a
    silent drop, never grows, never blocks. `pop()` → `optional<Envelope>`.
  - `Mailbox(AuditSink& = default_audit_sink(), subject)` (Rule 4b,
    latest-value-only) — single pending slot, `put()` →
    `PutOutcome{Stored, Overwrote}`; overwrite bumps `overwrites()`, calls
    `audit.record("mailbox_overwritten", subject, "superseded_seq=N")`.
    `take()` → `optional<Envelope>`.
  - **NOT thread-safe** (caller-synchronized, same as
    `harpia_capability_dispatch.h`). A threaded send path is a Phase 3b call.
  - No payload parsing / range checks (Rule 2).
  - `#include "harpia_audit_sink.h"` (its sibling in the same dir).
- **`Compliance/delivery_common.py`** — `DELIVERY_RUNTIME_SRC` path constant
  (mirrors `audit_common.py`); `DELIVERY_RUNTIME_DEPS` names the audit-sink
  header as a co-copy dependency (both must land in the same output dir).
- **`UnitTests/test_delivery_runtime.py`** — 10 g++-gated tests, `-Werror`,
  standalone-compile pattern (no generated project), incl. a Phase 3c
  rehearsal (stall overruns the queue → drain replays survivors in order →
  every loss audited via a counting test `AuditSink`).
- Docs: `Compliance/CLAUDE.md`, `UnitTests/CLAUDE.md`, roadmap updated.

Purely additive — no existing generator code touched, so golden tests cannot
drift from Phase 3a.

---

## What the next session must do

### Phase 3b — wire `ZmqAdapter` to the delivery runtime

Goal: a generated ZMQ transport for a `critical` message type routes its send
path through `BoundedQueue`; non-`critical` types are unchanged (or use
`Mailbox` where latest-value-only makes sense — decide per the design-rules
Rule 4 "ask the consumer" note, but the safe default for now is: `critical` →
queue, everything else → today's direct send).

- `ZmqAdapter/ZmqAdapter.py` (`Stage 13`) generates
  `<dest>/generated/cpp/zmq/<name>_<hash>_zmq.h`. Templates in
  `ZmqAdapter/templates/`. `_is_one_to_many(mods)` already reads
  `access_modifiers`; add the analogous `is_critical` read (`Message.is_critical`
  is on the object; `mods` in the adapter is a `set` of token-type strings via
  `_modifiers(msg)` — `"CRITICAL" in mods` also works).
- Copy `harpia_delivery.h` **and** `harpia_audit_sink.h` into the generated
  tree (use `Compliance.delivery_common.DELIVERY_RUNTIME_SRC` +
  `DELIVERY_RUNTIME_DEPS`; `copy_if_different` from `Util.util`). Decide the
  output dir — `generated/cpp/zmq/` alongside the transports, or a shared
  `generated/cpp/delivery/`. The capability runtime went to a shared
  `generated/cpp/capability/`; mirroring that is reasonable.
- The generated `<name>_sender` for a `critical` type: instead of `send()`
  serializing + firing the socket directly, it stamps an `Envelope`
  (`seq` from a per-sender counter, `crc` auto, timestamp optional), pushes
  into a `BoundedQueue` member, and a `flush()`/`pump()` drains the queue to
  the socket — so a transient socket failure leaves messages queued rather
  than lost. Keep the existing direct API working for non-critical types.
- Golden regen: `HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest
  UnitTests/test_golden.py UnitTests/test_golden_java.py` then **review the
  diff**. `alarm_event`'s `zmq/` output will change; existing messages'
  `zmq/` output must NOT (they're not `critical`).
- Structural unit test in `UnitTests/` (pure Python): the `alarm_event` zmq
  header wires the queue; a non-critical message's doesn't; the runtime
  headers are copied.

### Phase 3c — the `critical` send/receive integration test

Real ZMQ socket (`inproc://` or `tcp://`, `libzmq`+`cppzmq` are in the Docker
image — see `test_stage13_zmq.py` for the pattern). Simulate a stall
(receiver not bound yet / socket briefly unavailable), assert the `critical`
message is held in the bounded queue and replayed **in order** on reconnect, a
rotation event is audited when the queue overflows, and a non-`critical`
message on the same path is dropped rather than queued. This is one of the two
headline deliverables.

### Then — pivot to the `phi` side

Per the roadmap: **Track O** (key management — `Crypto/KeyProvider`, KEK/DEK
envelope encryption, rotation, crypto-shred; the big prerequisite) → **Track H**
(DB schema evolution — repeated-composed + non-additive transforms) → **Track A**
(`EncryptedColumn<T>` on `is_phi` columns + audit-on-access) → **Track F**
(`phi` redaction in JSON/XML/YAML `toString`; only needs F2, can be done any
time). Track A's persist→restart→read round-trip is the second headline test.

**Deferred groundwork**: a checked-in repo-root `project.harpia.yaml` — land it
with Track O (the first code that actually branches on `ComplianceContext`).
Adding it earlier risks silent interference with tests that assume the
missing-file/strictest path. See the roadmap Phase 0 note and the F1 section of
`epics/handoff-document.md`.

---

## Conventions / gotchas (bit you if you don't know them)

- **Run the full suite in Docker before every commit**:
  `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/harpia -v
  harpia-gradle-cache:/tmp/.gradle -w /harpia -e HOME=/tmp -e
  GRADLE_USER_HOME=/tmp/.gradle harpia-build pytest -q -p no:cacheprovider`.
  Do **not** use `Docker/run.sh` non-interactively — it passes `-it` and dies
  on non-TTY stdin. Baseline: **211 passed, ~4 skipped** (opt-in PG/KVM).
- **`.harpia` comments are lexed like code.** Backtick, apostrophe, `:`, `!`,
  `?`, `#`, `@`, `%`, `^`, `~` all hit `MISMATCH` and hard-error the whole
  file *even inside a `//` comment*. Stick to letters/digits/`. , ( ) { } [ ]
  ; = < > + - * /` and spaces. (Bit me writing the `alarm_event` fixture.)
- **Golden regen** honours `HARPIA_UPDATE_GOLDEN=1` on
  `test_golden.py`/`test_golden_java.py`. Editing `HarpiaTest/Include/*.harpia`
  is safe for the pinned `HASH` constants in `UnitTests/*.py` (only the ROOT
  `test.harpia`'s text feeds that hash) but does change golden content —
  regenerate and review. If you edit `test.harpia` itself, ~17 files pin the
  hash — see `UnitTests/CLAUDE.md` "The pinned HASH constant".
- **`AuditSink` operation strings are caller-owned**, not a Foundation enum —
  invent your own (`"message_sent"`, `"queue_rotated"`, …). `record()` has no
  parameter that can carry a field value (Rule 5, structural).
- Host has `g++` but not `protoc`/`pkg-config`/`cmake`, so
  `test_stage9`/`test_stage14`/`test_message_versioning_wire` fail on the host
  and pass in Docker — not regressions.
- Hidden-field names (`ID_<hash>` etc.) are md5-suffixed off the whole
  `.harpia` file text, so they move on any edit; `Message/FieldMap.py` keys
  wire numbers by role to keep them stable. Don't be alarmed by hidden-field
  name churn in a golden diff after editing a fixture.
