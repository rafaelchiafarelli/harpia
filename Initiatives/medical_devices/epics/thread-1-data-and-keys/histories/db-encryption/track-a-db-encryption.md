# Track A — DB field-level encryption + audit wiring

## Receives (must be done before this track starts)

- **F1, F2, F3** from Foundation (see `../thread-1-data-and-keys/README.md`)
  — `ComplianceContext`, the `field.is_phi` flag this track keys off of,
  and the `AuditSink` stub it wires calls into.
- **Every session in Track O** (`../key-management/track-o-key-management.md`,
  O.1–O.5) merged — this track's encrypt/decrypt path is built directly on
  Track O's `KeyProvider`.
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

## Watch for

- A.4 is Track O's O.5 matched pair — don't skip it thinking A.1–A.3's
  own tests already cover what O.5 deferred.
