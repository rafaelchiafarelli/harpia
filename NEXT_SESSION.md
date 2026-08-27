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
  `.../critical-delivery/tasks/` — all four carry a `-done` suffix:
  `critical-modifier-done.md` (D.1), `delivery-runtime-done.md` (D.2),
  `zmq-wiring-done.md` (D.3), `send-receive-integration-test-done.md`
  (D.4). The `-done` filename suffix IS the done marker — no status line
  inside, and don't edit a done task file.

The `phi` side is **not** re-tracked in thread-6 — it already has homes:
Track O / H / A / K in `thread-1-data-and-keys/`, Track F in
`thread-3-message-behavior/`.

`Initiatives/medical_devices/sensitive-data-implementation-roadmap.md` is the
original plan doc — **do not edit it.** thread-6 supersedes it for tracking.

## What this session did — Track O, Session O.1  ✅

`tasks/key-provider-interface-done.md` — the `KeyProvider` interface +
envelope-encryption shape (first `phi`-side session).

- `Crypto/runtime/harpia_key_provider.h` — hand-written C++ (not generated),
  `harpia::crypto`: `Dek` (`seal`/`open` — the DEK, and only the DEK,
  touches the value), `WrappedDek` (`kek_version` + `bytes`), `KeyProvider`
  ABC (`active_kek_version` / `generate_dek` / `wrap_dek` / `unwrap_dek` →
  `std::optional<Dek>` / `rotate`), `InMemoryKeyProvider` dummy (XOR, NOT
  crypto — for tests until O.2). `unwrap_dek` → `nullopt` on an unknown /
  forgotten KEK version (Rule 5; also the O.3 crypto-shred path).
- `Crypto/key_provider_common.py` — path constants (mirror
  `audit_common.py` / `delivery_common.py`). Nothing copies the header yet
  — Track A is the first consumer.
- `UnitTests/test_key_provider.py` — 8 g++-gated tests (`-Werror`):
  wrap/unwrap round trip, seal/open, version stamping, rotation keeps old
  DEKs unwrappable + mutates no existing `WrappedDek`, unknown/forgotten
  KEK version → `nullopt`, polymorphic use.
- Additive — no generator code touched, no golden impact. Host 166 passed;
  **full Docker suite 238 passed, 4 skipped.**

**Track-o restructured to match its siblings:** `histories/track-o-key-management.md`
→ `histories/key-management/track-o-key-management.md` (contract only) +
`histories/key-management/tasks/` (one file per session O.1–O.5). References
in `Initiatives/README.md`, `thread-1-data-and-keys/README.md`,
`track-a-db-encryption.md`, `thread-6-critical-and-phi/README.md` updated.

### Track D — complete (the `critical` arc)
- **D.1** `b433dd5` — `critical` modifier (lexer + `Message.is_critical`).
- **D.2** `3581933` — `Compliance/runtime/harpia_delivery.h` (`Envelope`,
  `BoundedQueue` Rule 4a, `Mailbox` Rule 4b still unwired).
- **D.3** `0e7e200` — `ZmqAdapter` routes a `critical` type's send path
  through `BoundedQueue`; runtime copied into `generated/cpp/delivery/`.
- **D.4** `287e01b` — `UnitTests/test_critical_delivery_roundtrip.py`: real
  `tcp://` socket, `alarm_event` held-then-replayed-in-order, overflow
  rotates+audits, non-critical sender has no queue.
- Remaining debt: a `ComplianceReport/` note, captured as a **Track M**
  task (`thread-4-platform-infra/histories/process-artifacts/tasks/critical-delivery-note.md`,
  blocked on M.1).

## What the next session must do — continue Track O

Per `thread-6-critical-and-phi/README.md`'s execution order. Track O lives
at **`thread-1-data-and-keys/histories/key-management/`** — contract in
`track-o-key-management.md`, one file per session in `tasks/`.

- **O.1 done** — `tasks/key-provider-interface-done.md`. `Crypto/runtime/harpia_key_provider.h`
  (`KeyProvider` ABC + `Dek`/`WrappedDek` + `InMemoryKeyProvider` dummy),
  `Crypto/key_provider_common.py`, `UnitTests/test_key_provider.py` (8
  g++-gated).
- **Next: O.2** — `tasks/default-local-provider.md`. A concrete default
  `KeyProvider` (platform-keystore/TPM-sealed local storage) + the
  fail-safe acknowledgment gate under a PHI-at-scale profile. Must pass
  O.1's contract tests unmodified.
- Then O.3 (crypto-shred), O.4 (zeroization + `AuditSink` wiring), O.5
  (KMS/HSM reference adapter). Track H
  (`histories/schema-evolution/track-h-schema-evolution.md`, H.1–H.3, no
  Foundation dependency — can run in parallel), then Track A
  (`histories/db-encryption/track-a-db-encryption.md`, A.1–A.4 —
  **delivers the `phi` send/receive headline test** at A.4), then Track K.
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
  Baseline after O.1: **238 passed, 4 skipped**.
- **One session = one file under the track's `tasks/`. When it lands,
  `git mv` that file to add a `-done` suffix — the filename is the done
  marker, no status line inside. Never edit a done task file** (only fix
  links that pointed at its old name). Use the epics naming (thread folder
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
