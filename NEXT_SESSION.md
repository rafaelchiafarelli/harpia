# NEXT_SESSION — sensitive-data implementation (`critical` + `phi`)

Branch: **`feature/sensitive-data-implementation`** (off `dev`, pushed).

## Where the work is tracked

`Initiatives/medical_devices/epics/thread-6-critical-and-phi/` — created
2026-08-27. `critical` never had a track in the master plan (the plan
assumed it was already built); this thread is that track plus the
coordination point for the two headline integration tests.

- **`thread-6-critical-and-phi/README.md`** — execution order for the whole
  sensitive-data effort + definition of done. Read first.
- **`thread-6-critical-and-phi/histories/critical-delivery/track-d-critical-delivery.md`**
  — the Track D contract. Sessions are one file each under
  `.../critical-delivery/tasks/` (`critical-modifier.md` D.1,
  `delivery-runtime.md` D.2, `zmq-wiring.md` D.3,
  `send-receive-integration-test.md` D.4). **All four done** — each task
  file's `**Status:**` line says so. Don't edit a done task file.

The `phi` side is **not** re-tracked in thread-6 — it already has homes:
Track O / H / A / K in `thread-1-data-and-keys/`, Track F in
`thread-3-message-behavior/`.

`Initiatives/medical_devices/sensitive-data-implementation-roadmap.md` is the
original plan doc — **do not edit it.** thread-6 supersedes it for tracking.

## What this session did — Track D, Session D.4  ✅

`UnitTests/test_critical_delivery_roundtrip.py` (protoc+g+++pkg-config+
libzmq+cppzmq-gated) — the `critical` send/receive headline integration
test. Drives the generated `alarm_event` transport over a real `tcp://`
socket:

1. **Held then replayed in order.** Publish 5 while the subscriber is
   absent — `publish()` only enqueues, `pending()` grows to 5, socket
   untouched. Subscriber joins, 300 ms settle (`_SETTLE_MS` — PUB/SUB slow
   joiner; `flush()` can't be retried), `flush()` sends all 5,
   `pending()==0`, received severity 1..5 in order.
2. **Overflow rotates + audits.** `queue_capacity=4`, 10-message burst
   through a `CountingSink`: `"queue_rotated"` fires exactly 6×,
   `queue().rotations()==6`, `pending()` stays 4, `flush()` delivers the
   newest 4 (severity 7..10) in order.
3. **Non-`critical` sender has no queue.** `courier_sender` has no
   `flush()`/`pending()`/`queue()` (detection traits) and `send()` stays
   synchronous `bool`.

`UnitTests/CLAUDE.md` updated (test entry + `test_critical_delivery_roundtrip.py`
added to the pinned-`HASH` file list). **Full Docker suite: 230 passed, 4
skipped.**

### Track D earlier
- **D.1** (`b433dd5`) — `critical` message-type modifier (lexer +
  `Message.is_critical`), AST flag only.
- **D.2** (`3581933`) — `Compliance/runtime/harpia_delivery.h`: `Envelope`
  (origin CRC-32 + seq), `check_on_arrival`, `BoundedQueue` (Rule 4a),
  `Mailbox` (Rule 4b, still unwired).
- **D.3** (`0e7e200`) — `ZmqAdapter` routes a `critical` type's zmq
  sender/publisher send path through `BoundedQueue`; runtime copied into
  `generated/cpp/delivery/`. Non-critical transports byte-identical.

Track D (the `critical` arc) is complete. Its one remaining debt — a
`ComplianceReport/` traceability note — is captured as a **Track M** task
(`thread-4-platform-infra/histories/process-artifacts/tasks/critical-delivery-note.md`,
blocked on Track M's M.1), not a Track D session.

## What the next session must do — the `phi` side

Per `thread-6-critical-and-phi/README.md`'s execution order:

- **`thread-1-data-and-keys/histories/track-o-key-management.md`** —
  Session **O.1** (`KeyProvider` interface + envelope-encryption shape).
  Preconditions F1/F3/F5 all merged. This is the first real `phi`-side
  session and the big prerequisite for Track A.
- Then O.2–O.5, Track H (`.../schema-evolution/track-h-schema-evolution.md`,
  H.1–H.3, no Foundation dependency — can run in parallel), then Track A
  (`.../db-encryption/track-a-db-encryption.md`, A.1–A.4 — **delivers the
  `phi` send/receive headline test** at A.4), then Track K.
- **`thread-3-message-behavior/histories/serialization/track-f-serialization.md`**
  — Track F (F.1–F.5), needs only F2, independent of everything above.
  Delivers the serialization/redaction half of the `phi` headline test.
- **`project.harpia.yaml`** (checked-in repo-root compliance config) lands
  with **Track O** — the first code that branches on `ComplianceContext`.
  Not earlier (silent test interference for no gain).

## Conventions / gotchas

- **Run the full suite in Docker before every commit**:
  `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/harpia -v
  harpia-gradle-cache:/tmp/.gradle -w /harpia -e HOME=/tmp -e
  GRADLE_USER_HOME=/tmp/.gradle harpia-build pytest -q -p no:cacheprovider`.
  Do **not** use `Docker/run.sh` non-interactively (`-it`, dies on non-TTY).
  Baseline after D.4: **230 passed, 4 skipped**.
- **One session = one file under the track's `tasks/`. When it lands, add
  the `**Status:** done — <commit>` line to that task file and nothing
  else. Never edit a done task file.** Use the epics naming (thread folder
  / track file / task file / session ID like `D.4`, `O.1`), not "Phase 3c".
  The `track-*.md` file holds only the contract (Receives / Gives / Files
  touched / Watch for).
- The `critical` zmq sender's API differs from the non-critical one on
  purpose: `send()`/`publish()` return `std::optional<PushOutcome>` and
  only enqueue — call `flush()` to transmit. Non-critical senders unchanged.
- One generated `*_zmq.h` per translation unit — two collide on the shared
  `runtime_origin_id()` helper.
- **`.harpia` comments are lexed like code.** Backtick, apostrophe, `:`,
  `!`, `?`, `#`, `@`, `%`, `^`, `~` hard-error the whole file *even inside a
  `//` comment*. Letters/digits/`. , ( ) { } [ ] ; = < > + - * /` and
  spaces only.
- Editing `HarpiaTest/Include/*.harpia` is safe for the pinned `HASH`
  constants (only root `test.harpia`'s text feeds that hash) but changes
  golden *content* — `HARPIA_UPDATE_GOLDEN=1` and review. Editing
  `test.harpia` itself → ~18 files pin the hash, see `UnitTests/CLAUDE.md`.
- `AuditSink` operation strings are caller-owned, not a Foundation enum.
  The delivery runtime uses `"queue_rotated"` / `"mailbox_overwritten"`.
- Host lacks `protoc`/`pkg-config`/`cmake`, so `test_stage9`/`test_stage14`/
  `test_message_versioning_wire`/`test_critical_delivery_roundtrip` fail on
  the host and pass in Docker — not regressions.
- The delivery runtime is **not thread-safe** (caller-synchronized). The
  zmq critical sender's `BoundedQueue` has no lock — a background flush
  thread is a future decision, not assumed.
