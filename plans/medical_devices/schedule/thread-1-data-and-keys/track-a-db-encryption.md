# Track A — DB field-level encryption + audit wiring

## Receives (must be done before this track starts)

- **F1, F2, F3** from Foundation (see `../thread-1-data-and-keys/README.md`)
  — `ComplianceContext`, the `field.is_phi` flag this track keys off of,
  and the `AuditSink` stub it wires calls into.
- **Every session in Track O** (`track-o-key-management.md`, O.1–O.5)
  merged — this track's encrypt/decrypt path is built directly on Track
  O's `KeyProvider`.
- **Every session in Track H** (`track-h-schema-evolution.md`, H.1–H.3)
  merged — a `phi` field living in a child table needs Track H's
  migration machinery in place before this track's schema can safely
  evolve.

## Gives (what "done" means here, consumed by whom)

- `EncryptedColumn<T>`-style wrapper, DAO encrypt-on-write/decrypt-on-read
  wiring, `AuditSink` wiring on every `phi`-touching CRUDL op, and a
  `ComplianceReport/` note describing the change.
- Closes out (A.4) the two Track O integration tests that couldn't be
  proven without a real DAO: the KEK-rotation round trip and the
  backend-swap-with-zero-DAO-changes proof.
- **Consumed by:** Track K (`track-k-db-segregation.md`) — shares the
  same `Database/` generator files this track modifies, starts
  immediately after. Also consumed by Track M (Session 4 — Platform
  Infra & Expansion, not yet restructured into this per-track format),
  which reads this track's `ComplianceReport/` note as raw material for
  its traceability matrix — a cross-thread consumer, flagged since it
  lives outside this folder.

## Files this track touches

- `Database/`, `model.py` (per `harpia_medical_master_plan.md` §2's track
  table). **Flag:** no more specific filenames than that are named in the
  plan docs for this track — not guessing further.

---

## Session A.1 — `EncryptedColumn<T>` wrapper + encrypt-on-write

- **Deliverable:** `EncryptedColumn<T>`-style wrapper used when
  `field.is_phi`, built on Track O's envelope-encryption scheme; DAO
  create/update paths encrypt-on-write via `KeyProvider`.
- **Guarantees:** `phi` values are never persisted in plaintext on the
  write path; non-`phi` fields see no behavior/perf change.
- **Out of scope:** decrypt-on-read (A.2), `AuditSink` wiring (A.3).
- **Tests:**
  - Unit: encrypt round trip per supported type.
  - Integration: write → persist → raw SQL query (bypassing the DAO)
    shows ciphertext, not plaintext.

## Session A.2 — Decrypt-on-read

- **Depends on:** A.1 merged.
- **Deliverable:** DAO read path decrypt-on-read via `KeyProvider`.
- **Tests:**
  - Unit: decrypt round trip per supported type.
  - Integration: write → persist → restart process → read; confirm
    decrypted value matches the original.

## Session A.3 — `AuditSink` wiring on `phi` CRUDL ops + `ComplianceReport` note

- **Depends on:** A.1, A.2 merged; F3's `AuditSink`.
- **Deliverable:** `AuditSink.record()` call at each DAO CRUDL operation
  touching a `phi` field; one-paragraph note added to `ComplianceReport/`
  describing what changed and why (feeds Track M later).
- **Tests:**
  - Unit: mock `AuditSink`, assert exactly one call per DAO op with
    correct field-level detail.

## Session A.4 — Full round-trip + cross-track acceptance gates

- **Depends on:** A.1–A.3 merged.
- **Deliverable:** nothing new to build — this session closes out the
  integration tests that could only be proven once Track A's DAO
  genuinely exists (deferred from Track O's O.5, not droppable):
  - Track O's KEK-rotation round trip: write → persist → rotate KEK →
    read both pre- and post-rotation data, confirming no full-database
    re-encryption occurred.
  - Track O's backend-swap proof: swap `KeyProvider` backend (O.2's
    default → O.5's reference adapter) with zero changes to this track's
    generated DAO code.
- **Acceptance gate:** existing non-`phi` CRUDL golden tests (14.1/14.2)
  unchanged.

## Watch for

- A.4 is Track O's O.5 matched pair — don't skip it thinking A.1–A.3's
  own tests already cover what O.5 deferred.
