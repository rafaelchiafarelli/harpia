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

### Phase 3b — wire `ZmqAdapter` to the delivery runtime  (this commit)

A `critical` message type's zmq **sender/publisher** now routes its send path
through `harpia::delivery::BoundedQueue` (design-rules Rule 4a). Non-`critical`
transports are byte-for-byte unchanged — the golden regen touched only
`alarm_event`'s header.

- **`ZmqAdapter/ZmqAdapter.py`** — `Process()` reads `msg.is_critical`
  (roadmap Phase 1a) and, per transport-bearing message, picks
  `sender_critical.tmpl` vs `sender.tmpl` for the sender/publisher fragment
  (the receiver/subscriber fragment is unchanged). When ≥1 critical
  transport message exists, copies `harpia_delivery.h` **and**
  `harpia_audit_sink.h` (its co-copy dependency, via
  `Compliance.delivery_common.DELIVERY_RUNTIME_DEPS`) into a shared
  `<dest>/generated/cpp/delivery/` — mirrors the capability runtime's
  `generated/cpp/capability/` home. A project with no critical transport
  message gets no new directory.
- **`ZmqAdapter/templates/sender_critical.tmpl`** (new) — same origin-id /
  CURVE / ORIGINATOR-stamp shape as `sender.tmpl`, but:
  - `send()`/`publish()` returns
    `::std::optional<::harpia::delivery::PushOutcome>` (empty iff the message
    could not be serialized at all), and **enqueues** a
    `harpia::delivery::Envelope::stamp(next_seq_++, bytes)` into a member
    `BoundedQueue queue_` instead of touching the socket. `next_seq_` starts
    at 1, per sender.
  - a new **`flush()`** drains the queue to the socket oldest-first
    (`peek()` → send → `pop()`), stopping at the first socket failure so a
    transient outage costs latency, not messages. Returns the count sent.
  - ctor gains `queue_capacity` (default 128) and
    `AuditSink& audit` (default `default_audit_sink()`) params, *before* the
    trailing defaulted CURVE-keys param. Audit subject is the message type
    name (`"alarm_event"`), so a `"queue_rotated"` record identifies the
    stream.
  - extra accessors: `pending()`, `queue()`.
- **`ZmqAdapter/templates/header.h.tmpl`** — gained an `{extra_includes}`
  slot right after the `.pb.h` include. `""` for non-critical (output
  identical to before); `#include "delivery/harpia_delivery.h"` for
  critical.
- **`Compliance/runtime/harpia_delivery.h`** — added
  `const Envelope* BoundedQueue::peek()` (non-destructive front look), so the
  `flush()` drain loop keeps queue order across a failed send. New assertion
  block in `UnitTests/test_delivery_runtime.py`.
- **`UnitTests/test_zmq_critical_delivery.py`** (new) — structural, pure
  Python (runs `run_pipeline.py`, no toolchain): critical publisher wires
  the queue + include + `flush()`; subscriber untouched;
  `courier`/`users` headers have zero `delivery::`/`BoundedQueue`; both
  runtime headers copied verbatim; a lone non-critical message creates no
  `delivery/` dir.
- Docs: `ZmqAdapter/CLAUDE.md`, `Compliance/CLAUDE.md`,
  `Compliance/delivery_common.py`, `UnitTests/CLAUDE.md`, roadmap updated.
- Goldens regenerated (`HARPIA_UPDATE_GOLDEN=1`): only
  `UnitTests/golden/zmq/alarm_event_3ac5d8b36fc7dcfb70888145147ddfb7_zmq.h`
  changed; root `HASH` unchanged (no `.harpia` edit).
- **Full Docker suite: 227 passed, 4 skipped.** Host: 158 passed, 4 failed
  (the known no-protoc/pkg-config/cmake host failures — not regressions), 69
  skipped.

### Earlier this branch
- **Phase 1a** (`b433dd5`) — `critical` message-type modifier (lexer +
  `Message.is_critical`), AST flag only.
- **Phase 3a** (`3581933`) — `Compliance/runtime/harpia_delivery.h`:
  `Envelope` (origin CRC-32 + monotonic seq, `crc_ok()`, `check_on_arrival`),
  `BoundedQueue` (Rule 4a), `Mailbox` (Rule 4b). Transport-agnostic; nothing
  consumed it until 3b.

---

## What the next session must do

### Phase 3c — the `critical` send/receive integration test  ← next

This is one of the two headline deliverables. Real ZMQ socket (`inproc://` or
`tcp://` — `libzmq`+`cppzmq` are in the Docker image; copy the compile/link
pattern from `UnitTests/test_stage13_zmq.py`, especially `_pkgconfig()` and
the `pb_cc` compile). The test targets the generated `alarm_event` publisher
(`critical event`, from `HarpiaTest/Include/file3.harpia`).

Assert, on a real socket:
1. **Held then replayed in order on reconnect.** Bind the subscriber late (or
   don't bind it until after several `publish()` calls). Each `publish()`
   returns `PushOutcome::Accepted` and `pending()` grows — nothing is on the
   wire yet. After the subscriber is up, `flush()` drains; the subscriber
   `receive()`s the envelopes **in seq order**. (Note the PUB/SUB "slow
   joiner" — `test_java_zmq.py` retries around it; for a deterministic test
   consider a short sleep after connect, or use PUSH/PULL by adding a
   `critical push` fixture message instead. `alarm_event` is `event`, i.e.
   PUB/SUB — decide whether to test it as-is with slow-joiner handling or add
   a `critical push message` to `file3.harpia`. Adding a fixture message
   means a golden regen + the "comments are lexed like code" gotcha below.)
2. **Overflow rotates + audits.** Construct the publisher with a small
   `queue_capacity` (e.g. 4), `publish()` more than that while "stalled",
   pass a counting `AuditSink` subclass (see the `CountingSink` in
   `test_delivery_runtime.py`) and assert `queue_rotated` fired exactly
   `N - capacity` times, `queue().rotations()` matches, and the survivors
   that `flush()` puts on the wire are the newest `capacity` in order.
3. **A non-`critical` message on the same kind of path is dropped, not
   queued.** e.g. `patient_vitals` (has no transport modifier though — you
   may need `courier` (push) or `users`) — its `send()` returns `bool` and
   fires the socket immediately, so with no receiver bound the message is
   just gone. Contrast: no `pending()`, no queue, no replay.

Wire it as a g+++libzmq-gated test (`test_stage13_zmq.py`'s `pytestmark`
skipif is the template). If you add a fixture message, bump the golden and
re-check the pinned-`HASH` file list (below) — though editing only
`Include/file3.harpia` (not the root `test.harpia`) leaves the pinned `HASH`
alone, only golden *content* moves.

Then a one-paragraph traceability note: `alarm_event` carries a `phi` field,
so Phase 3 is phi-adjacent per the roadmap DoD. `ComplianceReport/` doesn't
exist yet (Track M, Phase 5) — either stand up a minimal
`ComplianceReport/notes/` now or leave a TODO in the roadmap's Execution log
and write the note when Track M lands. Confirm with the owner which.

### Then — pivot to the `phi` side

Per the roadmap: **Track O** (key management — `Crypto/KeyProvider`, KEK/DEK
envelope encryption, rotation, crypto-shred; the big prerequisite) → **Track H**
(DB schema evolution) → **Track A** (`EncryptedColumn<T>` on `is_phi` columns
+ audit-on-access) → **Track F** (`phi` redaction in JSON/XML/YAML `toString`;
only needs F2, can be done any time). Track A's persist→restart→read
round-trip is the second headline test.

**Deferred groundwork**: a checked-in repo-root `project.harpia.yaml` — land
it with Track O (the first code that actually branches on `ComplianceContext`).
Adding it earlier risks silent interference with tests that assume the
missing-file/strictest path. See the roadmap Phase 0 note and the F1 section
of `epics/handoff-document.md`.

---

## Conventions / gotchas (bit you if you don't know them)

- **Run the full suite in Docker before every commit**:
  `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/harpia -v
  harpia-gradle-cache:/tmp/.gradle -w /harpia -e HOME=/tmp -e
  GRADLE_USER_HOME=/tmp/.gradle harpia-build pytest -q -p no:cacheprovider`.
  Do **not** use `Docker/run.sh` non-interactively — it passes `-it` and dies
  on non-TTY stdin. Baseline after Phase 3b: **227 passed, 4 skipped**
  (opt-in PG/KVM).
- **The critical zmq sender's API changed for critical types only**:
  `publish()`/`send()` no longer return `bool` and no longer touch the
  socket — they return `std::optional<PushOutcome>` and enqueue. Callers
  must call `flush()` to transmit. Non-critical senders are exactly as
  before. `test_stage13_zmq.py`'s `_CALLS` map does `(void)x.publish(m)`
  which still compiles fine against the optional return.
- **`.harpia` comments are lexed like code.** Backtick, apostrophe, `:`, `!`,
  `?`, `#`, `@`, `%`, `^`, `~` all hit `MISMATCH` and hard-error the whole
  file *even inside a `//` comment*. Stick to letters/digits/`. , ( ) { } [ ]
  ; = < > + - * /` and spaces.
- **Golden regen** honours `HARPIA_UPDATE_GOLDEN=1` on
  `test_golden.py`/`test_golden_java.py`. Editing `HarpiaTest/Include/*.harpia`
  is safe for the pinned `HASH` constants in `UnitTests/*.py` (only the ROOT
  `test.harpia`'s text feeds that hash) but does change golden content —
  regenerate and review. If you edit `test.harpia` itself, ~17 files pin the
  hash — see `UnitTests/CLAUDE.md` "The pinned HASH constant".
- **`AuditSink` operation strings are caller-owned**, not a Foundation enum.
  The delivery runtime uses `"queue_rotated"` / `"mailbox_overwritten"`;
  `record()` has no parameter that can carry a field value (Rule 5,
  structural).
- Host has `g++` but not `protoc`/`pkg-config`/`cmake`, so
  `test_stage9`/`test_stage14`/`test_message_versioning_wire` fail on the host
  and pass in Docker — not regressions.
- The delivery runtime is **not thread-safe** (caller-synchronized). The zmq
  critical sender is a plain member `BoundedQueue` with no lock — if Phase 3c
  or a later track needs a background flush thread, that's where the
  synchronization decision lands.
- Hidden-field names (`ID_<hash>` etc.) are md5-suffixed off the whole
  `.harpia` file text, so they move on any edit; `Message/FieldMap.py` keys
  wire numbers by role to keep them stable. Don't be alarmed by hidden-field
  name churn in a golden diff after editing a fixture.
