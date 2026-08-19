# Session 1 — Data & Keys

Covers Tracks O, H, A, K. **This session needs two people/repos running
concurrently at kickoff (O and H), converging into one for the rest
(A → K).** If you're picking this up, check which phase you're assigned
before starting.

---

## Preconditions

Foundation (F1–F5) merged to `main`. Confirm before starting:
- `ComplianceContext` is threaded through `main.py` and every stage.
- `field.is_phi` exists on parsed fields.
- `AuditSink` (no-op stub) exists and is injectable.
- `CryptoBackend` selection seam (F5) exists.
- A tagged F4 regression baseline exists — this is your diff target for
  every acceptance gate below.

---

## Execution order

**Phase 1a and 1b run in parallel, on two separate sessions/repos:**
- **1a — Track O** (Key management): no shared files with 1b, no
  functional dependency on it. Start immediately.
- **1b — Track H** (DB schema-evolution backlog): no shared files with
  1a, no functional dependency on it. Start immediately.

**Phase 1c starts only once both 1a and 1b are merged, one session:**
- **Track A** (DB field-level encryption), then **Track K** (public/
  private DB segregation) immediately after, same session — they share
  the same `Database/` generator files A just modified.

**If you finish 1a or 1b before the other is done:** don't idle. Pick up
a no-dependency task from Session 4 (Track J, Track M, or Track N's
static-analysis half) as filler until the other phase merges.

---

## Contracts

### Track O — Key management (pluggable `KeyProvider`, rotation, crypto-shredding)
- **Depends on:** F1, F3, F5.
- **Build this before Track A** — encryption without a real key-
  management story isn't something a medical device library can ship
  with.
- **Why this needs to be a library-level interface, not a fixed
  implementation:** Harpia is consumed by different manufacturers with
  different infrastructure — a hospital-integrated deployment may have
  its own KMS/HSM already; an embedded device may have none. The library
  defines the contract; the integrator supplies (or accepts a safe
  default for) the backend.
- **Decision closed: compile-time strategy.** Each jurisdiction build
  gets its own key-management behavior (retention, residency, audit
  shape) compiled in, not selected at runtime.
- **Deliverables:**
  - `Crypto/KeyProvider` abstract interface: generate/retrieve the active
    key-encryption-key (KEK), fetch a KEK by version, wrap/unwrap a
    data-encryption-key (DEK), rotate (new KEK version without touching
    existing data).
  - **Envelope encryption**, not direct KEK-encrypts-data: each `phi`
    column/record gets its own DEK; the KEK only wraps DEKs. This is what
    makes KEK rotation cheap (re-wrap DEKs, O(number of keys)) instead of
    a full re-encryption pass over the database (O(data size)).
  - A default, honest-about-its-limits `KeyProvider` (e.g. platform-
    keystore/TPM-sealed local storage) for integrators with no external
    KMS — but per the fail-safe-default rule, force acknowledgment (not
    silent use) when the compliance profile implies PHI at scale.
  - Documented extension point + at least one reference adapter to an
    external KMS/HSM class of system.
  - **Crypto-shredding:** permanently discard a specific DEK, rendering
    only that record's data unrecoverable without rewriting ciphertext —
    the practical mechanism for GDPR/LGPD-style right-to-erasure.
  - Key zeroization: key material cleared from memory after use.
  - Every key operation (generate, wrap, unwrap, rotate, shred) routed
    through `AuditSink`.
- **Guarantees after merge:** no key material ever appears in source code,
  generated config, or logs in plaintext; rotating the KEK never requires
  touching existing ciphertext; discarding a DEK is sufficient and
  necessary to make that DEK's data permanently unrecoverable; swapping
  the `KeyProvider` backend never requires changes to Track A's DAO code.
- **Explicitly out of scope — flag, don't silently drop:** FIPS 140-2/3
  (or equivalent) certification of the underlying crypto module is a
  deliberate library choice + separate certification process, not
  something this track completes as an engineering task.
- **Tests:**
  - Unit: envelope wrap/unwrap round trip; rotation produces a new KEK
    version while existing DEKs remain unwrappable via their version
    reference.
  - Unit: crypto-shred — discard a DEK, confirm ciphertext permanently
    unrecoverable even with the KEK.
  - Unit/CI: grep-style scan across generated output and logs asserting
    no raw key material ever appears in plaintext.
  - Integration: write → persist → rotate KEK → read both pre- and
    post-rotation data, confirming no full-database re-encryption.
  - Integration: swap `KeyProvider` backend with zero changes to Track A's
    generated DAO code.
  - Acceptance gate: Track A's encryption tests pass unmodified against
    either `KeyProvider` implementation.

### Track H — DB schema-evolution backlog
- **Depends on:** none (pre-existing debt, independent of compliance work).
- **Update (2026-08-18, current harpia `dev` @ `0757180`) — partially done,
  scope narrowed:**
  - RENAME/ADD/DROP/RETYPE (non-additive structural transforms) are
    **already implemented** — `renamed_from[<old>]` DSL modifier for
    rename, additive ALTER for add, an implicit runtime-diff for drop, and
    runtime-introspected type-mismatch detection for retype (no DSL marker
    needed). Don't re-plan or re-build these; see `Database/CLAUDE.md`'s
    `MigrationAdapter.py` bullet.
  - `migrate_<name>` also now takes an optional caller-supplied
    `std::function<void(::soci::session&)> data_transform` hook (runs
    after add, before drop) for **value**-level transforms an automatic
    diff can't express — e.g. deriving one column from another. This is
    directly relevant to Track A: encrypting/re-keying or reshaping `phi`
    columns across a schema version may need exactly this kind of value
    transform, not just a structural one. See `USAGE.md` §6.
  - **What's still genuinely missing** (the real remaining scope of this
    track): `MigrationAdapter._render()` only calls `analyze()`, which
    covers the *main* table's own columns — it never calls `map_fields()`
    or `repeated_fields()`, so migration never touches a message's child
    tables (map, repeated-scalar, *and* repeated-composed — all three
    kinds, not just repeated-composed). A live database with a stale
    child-table column set (e.g. an older repeated-composed schema) is
    never brought up to date by `migrate_<name>` today; only a fresh
    `create_table()` gets the current child-table shape.
- **Deliverables:** child-table (map/repeated/repeated-composed) schema
  migration support — extend the rename/add/drop/retype machinery (or a
  narrower equivalent) to each child table `MigrationAdapter` currently
  skips.
- **Guarantees:** `migrate_<table>()` correctly handles child-table schema
  changes without data loss outside what the transform itself specifies.
- **Tests:**
  - Unit: each child-table kind (map, repeated-scalar, repeated-composed)
    migrated in isolation.
  - Integration: old DB snapshot + new schema version → migrate → verify
    data integrity per transform semantics, for a message using each child
    table kind.
  - Acceptance gate: existing additive-migration and `data_transform`-hook
    tests unchanged.

### Track A — DB field-level encryption + audit wiring
- **Depends on:** F1, F2, F3, Track O, Track H (both merged first).
- **Deliverables:** `EncryptedColumn<T>`-style wrapper used when
  `field.is_phi`, built on Track O's envelope-encryption scheme; DAO
  create/read/update encrypt-on-write, decrypt-on-read via `KeyProvider`;
  `AuditSink.record()` at each DAO CRUDL op touching a `phi` field.
- **Guarantees:** `phi` values never persisted in plaintext; every DAO
  operation on a `phi`-bearing table emits exactly one audit record;
  non-`phi` fields see no behavior/perf change; KEK rotation never
  requires re-encrypting existing data, only re-wrapping DEKs.
- **Out of scope:** the `KeyProvider` implementation itself.
- **Tests:**
  - Unit: encrypt/decrypt round trip per supported type.
  - Unit: mock `AuditSink`, assert exactly one call per DAO op with
    correct field-level detail.
  - Integration: write → persist → restart process → read; confirm
    decrypted value matches original *and* a raw SQL query bypassing the
    DAO shows ciphertext, not plaintext.
  - Acceptance gate: existing non-`phi` CRUDL golden tests (14.1/14.2)
    unchanged.

### Track K — Public/private DB segregation
- **Depends on:** F1, Track A (same session, immediately after).
- **Deliverables:** environment-level registry distinguishing public vs.
  private databases per project.
- **Guarantees:** a private table is inaccessible cross-project; a public
  table remains accessible to any project with library access.
- **Tests:**
  - Unit: access-check denies cross-project private access.
  - Integration: two projects — one queries the other's public table
    (succeeds) and private table (denied).
  - Acceptance gate: existing single-project tests unaffected.

---

## Definition of done (applies to every track above)

- Unit tests for every new construct/behavior introduced.
- Integration test covering end-to-end behavior, not just isolated units
  (e.g. Track A: a full encrypt-write → read-decrypt round trip through
  the generated DAO).
- Full F4 regression baseline still passes.
- Track A specifically: one-paragraph note added to `ComplianceReport/`
  describing what changed and why (feeds Track M later).
- Once compile-time jurisdiction variants exist (after Track C lands in
  Session 2): Track N's feature-parity CI diff must pass for Track A/K.

## Watch for

- Don't start Track A until **both** Track O and Track H show a merged
  commit on `main` — starting against either alone means rebasing later.
- Track K starts immediately after Track A in the *same* session — don't
  hand it to a fresh session, it shares files with what A just touched.
