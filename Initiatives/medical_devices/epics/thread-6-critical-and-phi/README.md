# Thread 6 — `critical` delivery-guarantee + sensitive-data execution

Added 2026-08-27. Same structure as the other five threads (one file per
track, each broken into small `Session <Track>.<n>` units with an explicit
Receives/Gives/Files-touched contract).

**Why this thread exists.** `harpia_medical_master_plan.md` §5 and every
track that references it assume `critical` is *already built* ("the existing
critical/non-critical delivery-guarantee split", master plan §5;
"`critical` ... already fully handled", `../thread-5-device-interop/histories/fhir-facade/track-r-fhir-facade.md`).
It was not — Foundation F2 only ever shipped the `phi` field flag. The
`critical` message-type modifier, the delivery-guarantee runtime, and its
first transport wiring had no track anywhere. This thread is that track,
plus the coordination point for the two sensitive-data headline
integration tests.

- [track-d-critical-delivery.md](histories/critical-delivery/track-d-critical-delivery.md)
  — the contract. Sessions are one file each under
  `histories/critical-delivery/tasks/`: `critical-modifier.md` (D.1),
  `delivery-runtime.md` (D.2), `zmq-wiring.md` (D.3),
  `send-receive-integration-test.md` (D.4). The `phi`-adjacent
  `ComplianceReport/` note Track D owes is a **Track M** task —
  `../thread-4-platform-infra/histories/process-artifacts/tasks/critical-delivery-note.md`
  (that is Track M's module, blocked on M.1).

## The `phi` side is NOT re-tracked here

`phi` already has a home — don't duplicate it:

- **F2** (Foundation, done) — `field.is_phi` flag.
- **Track O** — `../thread-1-data-and-keys/histories/key-management/track-o-key-management.md`
  (key management: `KeyProvider`, envelope encryption, rotation,
  crypto-shred). Prerequisite for Track A.
- **Track H** — `../thread-1-data-and-keys/histories/schema-evolution/track-h-schema-evolution.md`
  (DB schema evolution). Prerequisite for Track A.
- **Track A** — `../thread-1-data-and-keys/histories/db-encryption/track-a-db-encryption.md`
  (`EncryptedColumn<T>` on `is_phi` columns + audit-on-access). **Delivers
  the `phi` send/receive headline test** (its A.4 acceptance gate:
  persist → restart → read; raw SQL shows ciphertext; one `AuditSink`
  record per phi DAO op).
- **Track F** — `../thread-3-message-behavior/histories/serialization/track-f-serialization.md`
  (`phi` redaction in JSON/XML/YAML `toString` + audited unredacted-output
  flag). Delivers the serialization half of the `phi` headline test. Only
  needs F2 — can run any time.

This thread's README carries the **execution order** for the whole
sensitive-data effort so it lives in one place; the per-track contracts
stay in the files above.

## Execution order (whole sensitive-data effort)

```
D.1 critical modifier  ──►  D.2 delivery runtime  ──►  D.3 ZMQ wiring  ──►  D.4 critical send/receive test
                                                                                    │
Track O  ──┐                                                                         │
Track H  ──┴──►  Track A  ──►  Track K                                               │
                                                                                    │
Track F  (needs F2 only, independent)                                                │
                                                                                    ▼
                                        both headline integration tests green
```

- The `critical` arc (D.1→D.4) has only D.1's own prerequisite (none) — it
  was taken first, as one self-contained arc, before the `phi` side.
- The `phi` side is Track O ∥ Track H → Track A → Track K, with Track F in
  parallel. See `../thread-1-data-and-keys/README.md` for that ordering.
- `project.harpia.yaml` (a checked-in repo-root compliance config) lands
  with **Track O**, not earlier — it's the first code that branches on
  `ComplianceContext`; adding it ahead of any consumer risks silent test
  interference. (Recorded here so it isn't re-litigated.)

## Definition of done (this whole effort — confirmed with the owner)

Stricter than "nothing old broke". Per master plan §4:

1. **Unit tests** for every new construct/behavior.
2. **Two headline integration tests:**
   - **`critical` send/receive** (this thread, D.4) — a `critical` message
     survives a simulated transient transport outage (held in the bounded
     queue, replayed in order on reconnect; rotation audited on overflow)
     while a non-`critical` message on the same path is allowed to drop.
   - **`phi` send/receive** (Track A's A.4 + Track F's F.5) — a `phi` field
     round-trips persist → process restart → read: decrypted value matches,
     a raw SQL query bypassing the DAO shows ciphertext, exactly one
     `AuditSink` record per DAO op touching the field; and
     `toString`/JSON/XML/YAML redact `phi` by default, the unredacted flag
     itself emitting an audit record.
3. `UnitTests/test_golden.py` (+ `test_golden_java.py`) regenerated and the
   diff reviewed.
4. A one-paragraph traceability note into `ComplianceReport/` for any work
   touching `phi`-adjacent code — written as a **Track M** task, since
   `ComplianceReport/` is Track M's module. Track D's is
   `../thread-4-platform-infra/histories/process-artifacts/tasks/critical-delivery-note.md`.

## Definition of done (every session in this thread)

- Unit tests for the construct/behavior that session introduces.
- One integration test for a session that closes an end-to-end path (D.4).
- Full regression baseline still passes — run the whole suite in Docker
  before every commit (`NEXT_SESSION.md` has the invocation; baseline
  after D.4 is **230 passed, 4 skipped**).
- **Ground Rule 6:** any session that touches a consumer-facing
  template/adapter emits/updates Doxygen doc-comments for what it touched,
  same session.

## Fixture

`HarpiaTest/Include/file3.harpia` — `alarm_event` (`critical event message`,
carries a `phi` field, added by D.1) and `patient_vitals` (the `phi`
fixture). Extend these rather than forking parallel fixtures.

## Watch for

- **`.harpia` comments are lexed like code.** Backtick, apostrophe, `:`,
  `!`, `?`, `#`, `@`, `%`, `^`, `~` all hit `MISMATCH` and hard-error the
  whole file *even inside a `//` comment*. Stick to letters/digits/`. , ( )
  { } [ ] ; = < > + - * /` and spaces.
- Editing `HarpiaTest/Include/*.harpia` is safe for the pinned `HASH`
  constants in `UnitTests/*.py` (only the ROOT `test.harpia`'s text feeds
  that hash) but does change golden *content* — regenerate
  (`HARPIA_UPDATE_GOLDEN=1`) and review.
- The delivery runtime is **not thread-safe** (caller-synchronized, same
  contract as `harpia_capability_dispatch.h`). A background flush thread is
  a future decision, not assumed.
