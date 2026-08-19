# Harpia → Medical-Device-Grade: Master Implementation Plan

Status as of: 2026-08-19
Scope: all outstanding work — both pre-existing Harpia backlog and the new
medical-device compliance work — organized so it can be parallelized safely
across multiple repo copies / devices / sessions without collisions.

---

## 0. Ground rules for parallel work

1. **Foundation lands first, alone, before anything else branches.** Every
   parallel track below depends on the `ComplianceContext` object and the
   `phi` DSL tag existing. Don't start a parallel track against a repo copy
   that doesn't have Foundation merged yet — you'll be rebasing against a
   moving target.
2. **One track = one module footprint, wherever possible.** Tracks are
   grouped below specifically so that two tracks running concurrently touch
   *different* files. Where that's not fully achievable, it's flagged
   explicitly in the "Coordinate with" column.
3. **Interfaces before implementations.** `AuditSink` is defined as an
   abstract/no-op stub in Foundation. Every other track that needs auditing
   (DB layer, comm layer) wires calls to that interface independently — this
   is what lets DB hardening and transport hardening run in parallel instead
   of both waiting on a single "audit track."
4. **Naming convention for branches/repo copies**, to keep it legible across
   sessions: `track-<ID>-<short-name>`, e.g. `track-C-transport-mtls`. Where
   a track ID has multiple rows (e.g. Track B, Track C below), use one
   branch per row if worked separately, or one branch covering both rows if
   worked in the same session — either way, keep the track ID as the prefix.
5. **Merge order matters more than merge speed.** A track marked
   "Coordinate with X" should merge *after* X, even if it finishes first.

---

## 0a. One hardened profile, not per-jurisdiction variants (decided 2026-08-19)

Two decisions supersede the "compile-time strategy: one build variant per
listed jurisdiction" language that the rest of this doc was originally
written with (F1, F3, F5, Track O, Track C, Track N's parity diff). Read
every per-track contract below with these corrections in mind rather than
as originally scoped:

1. **No jurisdiction fan-out in code.** FDA, EU MDR, and ANVISA converge on
   the same underlying standards (IEC 62304, ISO 14971) for Class-C-
   equivalent software — see `harpia_sensitive_data_design_rules.md` §6.
   The one identified delta (EU MDR's tamper-evident audit-log requirement)
   is simply made the universal default instead of gated behind an EU-only
   flag. There is exactly **one** generated code path per project, never
   one per jurisdiction. `jurisdiction[]` still exists in
   `project.harpia.yaml`, but purely as metadata Track M reads to pick
   which paperwork template (fda/eu_mdr/anvisa) the same evidence gets
   stamped into — it never forks a build variant. Track N's cross-
   jurisdiction "feature-parity diff" job is dropped entirely: with one
   code path, there is nothing to diff.
2. **`risk_class` sets one project-wide floor; `phi`/`critical` are opt-in
   on top of it.** Per IEC 62304 §4.3's segregation rule: if a lower-class
   software item isn't (or can't be proven) segregated from a higher-class
   item sharing the same binary, the *whole* item is classified at the
   higher class. A generated project mixing an untagged (Class A) message
   with a `phi`/`critical` (Class C) message on the same transport/process
   is exactly that unsegregated case. So once *any* message/field in a
   project is tagged, `risk_class` forces the **entire generated project**
   onto the hardened floor — mTLS/RBAC required, plaintext transport
   refused (Track C, Track B), tamper-evident audit storage present. This
   floor is project-wide, never per-message. `phi`/`critical` then layer
   the genuinely opt-in, finer-grained machinery on top of that floor:
   envelope encryption + redaction only on `phi` fields (Track A/F),
   ordered-delivery queues only on `critical` message types (see the
   design-rules doc's Rule 4a) — forcing an ordered-delivery queue onto
   untagged telemetry would be pure cost against a hazard that doesn't
   exist there.
3. **No tags anywhere → today's Harpia, byte-for-byte.** A project with no
   `phi`/`critical`/`risk_class` declared at all generates exactly what
   Harpia generates today (F2's existing guarantee, unchanged). The
   hardened floor only activates once the schema actually claims medical-
   device-grade status.

---

## 1. Foundation (serial — do this first, single session)

| ID | Task | Touches | Notes |
|---|---|---|---|
| F1 | `ComplianceContext`: parse `project.harpia.yaml` (`risk_class`, `topology`, `phi_handling`, `jurisdiction[]` — paperwork routing only), thread it through `main.py` and every stage entry point | `main.py`, every `Stage*` entry signature | Highest blast radius in the whole plan — every later track depends on this signature existing. Fail-safe default (strictest settings) when unset/ambiguous. `risk_class` is the single project-wide hardening floor — no per-jurisdiction build variants, no fan-out (see §0a). `jurisdiction[]` has zero effect on generated code; it only feeds Track M's doc-template selection. |
| F2 | `phi` (sensitive-field) modifier in the grammar + AST | `LexicalAnalizer/`, `Message/` | Needed before DB encryption, redacted `toString`, or audit-on-access can be built. |
| F3 | `AuditSink` interface — abstract/no-op stub only, no implementation yet | new `Compliance/` module | Real implementations happen in Track A (DB) and Track C (comm), independently, once this interface exists. One implementation per project, gated by `risk_class`, not per jurisdiction (see §0a) — build the stub already shaped for that. |
| F4 | Golden-snapshot / regression baseline confirmed green before anything branches | `tests/` | So every track has a clean starting point to diff against. |
| F5 | `CryptoBackend` selection point: the compile-time seam choosing which underlying crypto module gets linked (e.g. standard vs. FIPS-validated OpenSSL) | new `Crypto/backend.py` (or build-flag/CMake option) | Both Track O (key-wrap/envelope-encryption primitives) and Track C (TLS stack) must consume this, not each pick their own — prevents the two from silently drifting onto different crypto modules. One selection per project, driven by `risk_class`/`topology`, not per jurisdiction (see §0a). |

**Exit criterion:** F1–F5 merged to `main`, all existing tests green, before any track below starts.

---

## 2. Parallel tracks (post-Foundation)

Each row: what it does, what it touches, what it depends on, what it must
coordinate with. Where a track has multiple rows (Tracks B and C), the rows
are worked in the same session — split across sessions only if the
"Coordinate with" column says otherwise.

| ID | Track | Touches | Depends on | Coordinate with |
|---|---|---|---|---|
| O | Key management: pluggable `KeyProvider` interface, envelope encryption (KEK/DEK), rotation, crypto-shredding, key-access auditing | new `Crypto/` module | F1, F3, F5 | Runs in a separate, parallel session from H — no shared files, no functional dependency between them. |
| H | DB schema-evolution backlog: repeated composed fields, non-additive transforms (rename/drop/type-change) | `Database/` | none (pre-existing debt, independent of compliance work) | Runs in a separate, parallel session from O. |
| A | DB field-level encryption for `phi` columns + audit-on-read/write wiring into DAO | `Database/`, `model.py` | F1, F2, F3, O, H | Starts only once O and H are both merged. Same session as K, which follows immediately after. |
| K | Public/private DB segregation at environment level | `Database/` | F1, A | Same session as A, immediately after — shares the same generator files. |
| B | ZMQ CURVE security | `ZmqAdapter/` | F1 | Same session as the other B row (below) — both touch the same files. |
| B | Full `stream[#]` lifecycle (setup/read/stop, timeout, dead-connection reclamation) | `ZmqAdapter/` | F1 | Same session as the other B row (above). |
| C | mTLS transport (gRPC/REST/SOAP) | `ProtoFile/` (GrpcCompiler), `Assets/`, generated gate code | F1, F3, F5 | Same session as the other C row (below) — both rewrite the same credential-gate call sites. |
| C | RBAC (admin/main/guest, replacing the flat `X-User`/`X-Pswd` gate) + token-based sessions + cert provisioning | `ProtoFile/`, `Assets/`, generated gate code | F1, F3, F5 | Same session as the other C row (above). |
| E | Events/callbacks framework (`event[cached/not-cached]`, detached-thread callbacks) with `AuditSink` hooks at OnChange | `Logger/`, new `Callback/` module | F1, F3 | none directly, but logically depends on F3's interface shape |
| F | Serialization unification: add YAML pretty-print, close out the JSON/XML/YAML `toString` triad through one shared path, wire `phi` redaction into it | `JsonAdapter/`, `XmlAdapter/`, new `YamlAdapter/`, `Message/` toString templates | F2 | none |
| I | sha256-registry / continuable-process machinery (the "largely aspirational" architecture.md system) | `Util/`, `Logger/`, `main.py` orchestration | F1 | Same session as L, run right after Foundation — both touch `main.py` orchestration and the registry's version-stamp fields. |
| L | Versioning/git integration (per-project fork tracking) | `Util/`, `main.py` | F1 | Same session as I, immediately after. |
| M | Process artifacts: SBOM, traceability matrix, jurisdiction-selected risk-file/doc templates (fda/eu_mdr/anvisa) — same underlying evidence, different paperwork shell | new `ComplianceReport/` module | F1 | Benefits from I landing first but doesn't hard-block on it. |
| N | Static/fuzz analysis CI (cppcheck/clang-tidy CERT ruleset on generated output, fuzz harness for JSON/XML/SOAP parsers) | `tests/`, CI config only | none | Pure tooling, safe anywhere, anytime. |
| J | Multi-language codegen, first target language only (**Python** — see `plans/multi-language-targets.md`, don't re-derive) — reuses `protoc`/`grpc`'s native multi-language message/stub generation for Stages 0–7; only Stages 8–14 (DB/DAO, JSON/XML/SOAP/REST, ZMQ, auth, audit) need per-language emitters | new per-language emitter dirs, mirroring `Database/`, `JsonAdapter/`, etc. | F1 | none — prove the plugin-style split with one language before replicating to a second/third. Don't extrapolate Python's cost analysis to Rust/Node/Java ahead of time (rejected 2026-08-18 — see the detailed contract below). |

---

## 3. Four parallel sessions

**Precondition for all four:** Foundation (F1–F5) is built once, serially,
and merged/pulled into all four repo copies before any session begins. This
is the one synchronization point everyone waits on at the start.

### Session 1 — Data & Keys
Track O and Track H run in parallel first — two separate sessions, since
neither shares files with the other nor depends on it functionally. Once
both merge, **one** session runs Track A then Track K sequentially — A
needs both O and H merged first; K shares A's files immediately after.

This means Data & Keys briefly needs **two** of the four sessions at once
at kickoff, not one. See "Squaring the numbers" below for how that fits
inside four total sessions.

### Session 2 — Transport & Access
Track C (both rows) → Track B (both rows). No hard dependency between C
and B — order is for focus, not correctness — but keep them on one
session, since Track C sets the credential/session model the rest of the
comm layer should stay consistent with.

### Session 3 — Message Behavior
Track E → Track F. Events/callbacks before serialization — Track F's
redaction hook design benefits from seeing Track E's audit-hook pattern
already in place, though it's not a hard blocker.

### Session 4 — Platform Infra & Expansion
Track I → Track L (share `main.py`, must stay sequential) → Track J /
Track M / Track N, in any order — no dependencies among them now that
Track N no longer carries a cross-variant parity diff (§0a dropped it,
since there's only one code path to test).

### Squaring the numbers
Data & Keys needs two sessions at kickoff (O and H), which — together with
Session 2 starting on Track C and Session 3 starting on Track E — accounts
for all four sessions on day one. Session 4's work doesn't get a dedicated
session yet: whichever of O or H finishes first should pick up a
no-dependency Session-4 task (J, M, or N) as filler rather than idling
while it waits on the other. Once both O and H are merged, redirect one
session to Track A → Track K; the other keeps going on whatever Session-4
task it picked up.

---

## 4. Definition of done (per track)

A track is mergeable only when **all** of the following hold — passing the
pre-existing regression suite alone is not sufficient, since that only
proves nothing old broke, not that the new thing works:

- **Unit tests** for every new construct/behavior the track introduces
  (matching the existing per-message unit-test pattern from Stage 14 —
  e.g. a new `phi` field needs its own encryption/redaction unit test, not
  just coverage-by-association from an existing message test).
- **Integration test** covering the track's end-to-end behavior in a
  realistic path (e.g. Track C: an actual mTLS handshake + RBAC-gated
  request over the wire, not just unit tests of the cert-loading code in
  isolation; Track A: a full encrypt-write → read-decrypt round trip
  through the generated DAO, not just the encryption function alone).
- The full pre-existing regression suite (F4 baseline) still passes.
- For any track touching `phi`-adjacent code (A, C, E, F): a one-paragraph
  note added to `ComplianceReport/` describing what changed and why, so
  Track M's traceability work has raw material to draw from later instead
  of reconstructing history after the fact.
- For Tracks A/C/K specifically, once the `risk_class` hardened floor is in
  place: Track N's static/fuzz CI job passes clean against the generated
  output.

---

## 5. Per-track contracts

Each contract: what must already be true to start, what this track hands
back, what invariant it guarantees once merged, what it explicitly does
*not* touch (to keep it out of another track's files), and how it's
proven — unit + integration, not just "tests pass."

### F1 — ComplianceContext plumbing
- **Preconditions:** none (first thing built).
- **Deliverables:** `Compliance/context.py` (or equivalent) defining
  `ComplianceContext{risk_class, topology, phi_handling, jurisdiction[]}`;
  `project.harpia.yaml` parser; `main.py` and every `Stage*` entry point
  updated to receive it.
- **Guarantees after merge:** every stage has access to the active
  compliance profile; an invalid/unknown enum value is a hard error at
  generation start, never silently ignored; missing config defaults to the
  strictest profile with a logged warning; `risk_class` drives one project-
  wide hardened floor — never a per-jurisdiction fan-out (see §0a);
  `jurisdiction[]` is inert for codegen, read only by Track M.
- **Out of scope:** no `risk_class`-driven *behavior* yet — plumbing only.
- **Tests:**
  - Unit: valid config parses correctly; missing file → strictest default;
    invalid enum value → hard error.
  - Integration: run the full pipeline against `HarpiaTest/test.harpia`
    with a compliance config present; confirm every stage received the
    context (e.g. a per-stage smoke marker).
  - Acceptance gate: F4 baseline unaffected when no config file is present
    (backward-compatible default path).

### F2 — `phi` field modifier
- **Preconditions:** none structurally, but land in the same session as F1.
- **Deliverables:** grammar + AST support for `phi` in
  `LexicalAnalizer/`/`Message/`; `field.is_phi` flag available to every
  later stage.
- **Guarantees:** fields without `phi` behave exactly as before, byte-for-
  byte; `phi` composes correctly with existing modifiers (`optional`,
  `repeteable`, etc.).
- **Out of scope:** no encryption, redaction, or audit logic — flag only.
- **Tests:**
  - Unit: parse messages with/without `phi`, alone and combined with other
    modifiers; confirm AST flags.
  - Integration: Stages 0–6 on a `.harpia` file with `phi` fields produce a
    clean `.proto` with no unintended leakage of the tag into the wire
    schema (unless that's the intended design — confirm which).
  - Acceptance gate: existing snapshot tests for non-`phi` messages
    unchanged.

### F3 — AuditSink interface (stub)
- **Preconditions:** F1 merged.
- **Deliverables:** abstract `AuditSink` interface + `NoOpAuditSink`
  default implementation; documented injection point for downstream tracks.
- **Guarantees:** interface compiles and instantiates standalone; no-op
  implementation has zero side effects.
- **Out of scope:** real audit logic — that's built once, gated by
  `risk_class`, in Track O and Track C, not here.
- **Tests:**
  - Unit: `NoOpAuditSink.record()` called, asserts no side effect, no crash.
  - Integration: instantiate and inject into a dummy generated class,
    confirm no build/runtime error.

### F4 — Regression baseline
- **Preconditions:** none.
- **Deliverables:** tagged, CI-recorded green baseline of the existing test
  suite, used as the diff target for every later track's acceptance gate.
- **Guarantees:** every subsequent track's "acceptance gate" line refers
  back to this exact baseline.

### F5 — CryptoBackend selection point
- **Preconditions:** F1 merged. Build alongside F3 — same shape of
  decision (an interface stub now, real `risk_class`-driven selection once
  RA confirms the requirements).
- **Deliverables:** a single compile-time seam (build flag/CMake option)
  choosing which underlying crypto module a build links against (e.g.
  standard OpenSSL vs. a FIPS-validated OpenSSL provider). Both Track O's
  envelope-encryption primitives and Track C's TLS stack consume this same
  seam — neither is allowed to independently link its own crypto module.
- **Guarantees:** exactly one crypto module is linked per project; Track O
  and Track C provably use the same one (see test below); the choice is
  recorded as build metadata, feeding Track M's SBOM (which crypto module +
  its validation status, e.g. "FIPS 140-3 validated: yes/no," per shipped
  binary).
- **Out of scope:** doesn't ship or validate the crypto modules themselves
  — just the seam. Which specific modules to support (and any FIPS/Common
  Criteria certification work) is a deliberate downstream decision, not
  implied by building this seam.
- **Tests:**
  - Unit: build-flag selection actually changes which module gets linked
    (symbol/version check on the compiled artifact).
  - Integration: build with each supported crypto module, confirm both
    Track O and Track C functionality work identically against each (same
    algorithms, same outcomes, only the underlying validated implementation
    differs).
  - Acceptance gate: a CI check asserting Track O and Track C agree on
    which crypto module is linked within the same build — a drift here
    should fail the build.

### O — Key management (pluggable `KeyProvider`, rotation, crypto-shredding)
- **Preconditions:** F1, F3, F5 merged. Build this *before* Track A —
  encryption without a real key-management story isn't something a medical
  device library can ship with, so it can't stay a footnote on Track A.
- **Why this needs to be a library-level interface, not a fixed
  implementation:** Harpia is consumed by different manufacturers with
  different infrastructure — a hospital-integrated deployment may have its
  own KMS/HSM already; an embedded device may have none. The library must
  not assume either. It defines the contract; the integrator supplies (or
  accepts a safe default for) the backend.
- **Decision closed: compile-time strategy.** Key-management behavior
  (retention, residency, audit shape) is compiled in per project, not
  selected at runtime — same reasoning as Track C. One behavior per
  project, gated by `risk_class`, not forked per jurisdiction (§0a).
- **Deliverables:**
  - `Crypto/KeyProvider` abstract interface: generate/retrieve the active
    key-encryption-key (KEK), fetch a KEK by version, wrap/unwrap a
    data-encryption-key (DEK), rotate (produces a new KEK version without
    touching existing data).
  - **Envelope encryption**, not direct KEK-encrypts-data: each `phi`
    column/record gets its own DEK; the DEK is what actually encrypts the
    value; the KEK only wraps DEKs. This is what makes KEK rotation cheap
    (re-wrap DEKs, O(number of keys)) instead of requiring a full
    re-encryption pass over the database (O(data size)) — non-negotiable
    at any real data volume.
  - A default, honest-about-its-limits `KeyProvider` implementation (e.g.
    platform-keystore/TPM-sealed local storage) for integrators with no
    external KMS — but per the fail-safe-default rule already in this
    plan, the default should force acknowledgment (not silent use) when
    the active compliance profile implies PHI at scale, prompting an
    explicit KMS integration decision rather than quietly shipping the
    fallback into production.
  - Documented extension point + at least one reference adapter to an
    external KMS/HSM class of system (exact vendor TBD — the point is
    proving the interface is real, not picking a vendor here).
  - **Crypto-shredding support:** the ability to permanently discard a
    specific DEK, rendering only that record's data unrecoverable without
    touching or rewriting the ciphertext itself — this is the practical
    mechanism for GDPR/LGPD-style right-to-erasure requests without a
    destructive rewrite of the database.
  - Key zeroization: key material cleared from memory after use, not left
    to garbage collection/deallocation timing.
  - Every key operation (generate, wrap, unwrap, rotate, shred) routed
    through `AuditSink` — key management is itself a security-relevant,
    auditable activity, not exempt from Track A/E's audit requirement.
- **Guarantees after merge:** no key material ever appears in source code,
  generated config, or logs in plaintext (this is mechanically checkable,
  see tests below); rotating the KEK never requires touching existing
  ciphertext; discarding a DEK is sufficient and necessary to make that
  DEK's data permanently unrecoverable; swapping the `KeyProvider` backend
  never requires changes to generated DAO code in Track A.
- **Explicitly out of scope — flag, don't silently drop:** **FIPS 140-2/3
  (or equivalent) certification of the underlying cryptographic module**
  is not something this track can complete as an engineering task — it's a
  choice of which crypto library you build on (e.g. a FIPS-validated
  OpenSSL module) plus a separate certification process. This track should
  make that choice deliberately and document it, not default to whatever's
  convenient.
- **Tests:**
  - Unit: envelope wrap/unwrap round trip; rotation produces a new KEK
    version while existing DEKs remain unwrappable via their recorded
    version reference.
  - Unit: crypto-shred test — discard a DEK, confirm its ciphertext is
    permanently unrecoverable even with the KEK.
  - Unit/CI: a grep-style scan across generated output and logs asserting
    no raw key material ever appears in plaintext.
  - Integration: write → persist → rotate KEK → read both pre- and
    post-rotation data successfully, confirming no full-database
    re-encryption occurred (only DEK re-wrap).
  - Integration: swap the `KeyProvider` backend (default local
    implementation → a mock external KMS) with zero changes to
    Track A's generated DAO code — proves the interface boundary is real.
  - Acceptance gate: Track A's encryption tests pass unmodified when run
    against either `KeyProvider` implementation.

### H — DB schema-evolution backlog
- **Preconditions:** none (pre-existing debt). Runs in a separate, parallel
  session from Track O (see §3); Track A starts only once both are merged.
- **Deliverables:** repeated-composed-field migration support;
  non-additive transform support (rename/drop/type-change).
- **Guarantees:** `migrate_<table>()` correctly handles the new transform
  types without data loss outside what the transform itself specifies
  (e.g. a drop is expected to drop, but a rename must preserve data).
- **Tests:**
  - Unit: each new transform type in isolation.
  - Integration: old DB snapshot + new schema version → migrate → verify
    data integrity per transform semantics.
  - Acceptance gate: existing additive-migration tests unchanged.

### A — DB field-level encryption + audit wiring
- **Preconditions:** F1, F2, F3, O, H merged. Runs immediately after
  Track H in the same session (see §3); Track K follows in the same
  session right after this one.
- **Deliverables:** `EncryptedColumn<T>`-style wrapper used when
  `field.is_phi`, built on Track O's envelope-encryption scheme (encrypts
  with a per-table/per-record DEK, never directly with the KEK); DAO
  create/read/update encrypt-on-write, decrypt-on-read via `KeyProvider`;
  `AuditSink.record()` call at each DAO CRUDL op touching a `phi` field.
- **Guarantees:** `phi` values are never persisted in plaintext; every DAO
  operation on a `phi`-bearing table emits exactly one audit record;
  non-`phi` fields see no behavior/perf change; KEK rotation (Track O)
  never requires this layer to re-encrypt existing data, only re-wrap DEKs.
- **Out of scope:** the `KeyProvider` implementation itself — consumed as
  an interface from Track O, not built here.
- **Tests:**
  - Unit: encrypt/decrypt round trip per supported type.
  - Unit: mock `AuditSink`, assert exactly one call per DAO op with correct
    field-level detail.
  - Integration: write → persist → restart process → read; confirm
    decrypted value matches original *and* a raw SQL query against the DB
    (bypassing the DAO) shows ciphertext, not plaintext.
  - Acceptance gate: existing non-`phi` CRUDL golden tests (14.1/14.2)
    unchanged.

### K — Public/private DB segregation
- **Preconditions:** F1, A merged. Runs immediately after Track A, same
  session (see §3) — shares the same generator files.
- **Deliverables:** environment-level registry distinguishing public vs.
  private databases per project.
- **Guarantees:** a private table is inaccessible cross-project; a public
  table remains accessible to any project with library access.
- **Tests:**
  - Unit: access-check denies cross-project private access.
  - Integration: two projects — one queries the other's public table
    (succeeds) and private table (denied).
  - Acceptance gate: existing single-project tests unaffected.

### B — ZMQ CURVE security + full stream lifecycle
- **Preconditions:** F1 merged.
- **Deliverables:** CURVE keypair provisioning in `Assets/`; CURVE-secured
  ZMQ sockets; full `stream[#]` lifecycle (setup/read/stop, timeout,
  dead-connection reclamation) per the process.md spec.
- **Guarantees:** plaintext ZMQ refused by default when the compliance
  profile requires it; `read` returns IN-VALID on timeout/stop per spec;
  abandoned connections are reclaimed within the configured window.
- **Out of scope:** gRPC/REST/SOAP transport (Track C's job).
- **Tests:**
  - Unit: invalid stream config → IN-VALID; CURVE handshake rejects
    mismatched keys.
  - Integration: rerun the existing client/server ZMQ demo with CURVE
    enabled; add a dead-connection/timeout scenario.
  - Acceptance gate: existing ZMQ demo test still passes when the profile
    doesn't require CURVE (backward compatible).

### C — Transport (mTLS) + AuthN/AuthZ (RBAC, sessions)
- **Preconditions:** F1, F3, F5 merged.
- **Decision closed: compile-time strategy** — transport/auth behavior is
  compiled in per project rather than selected at runtime (same reasoning
  as Track O; see F3). Once `risk_class` implies medical-device-grade, this
  is the project-wide floor (§0a): every message gets mTLS/RBAC, not just
  `phi`/`critical`-tagged ones.
- **Deliverables:** mTLS on gRPC/REST/SOAP; admin/main/guest RBAC
  replacing the flat `X-User`/`X-Pswd` gate; token-based sessions with
  expiry/revocation; cert provisioning scripts in `Assets/`.
- **Guarantees:** plaintext connections refused by default per profile;
  role-based access enforced at the gate with differentiated 401
  (unauthenticated) vs. 403 (wrong role); sessions expire and can be
  revoked.
- **Out of scope:** ZMQ transport.
- **Tests:**
  - Unit: full role × operation permission matrix (allow/deny table).
  - Unit: token expiry and revocation logic.
  - Integration: live REST/gRPC/SOAP calls over TLS with client certs —
    confirm 401 with no cert, 403 with wrong role, 200 with correct role.
  - Acceptance gate: existing HTTP tests (14.7–14.10) updated to run over
    TLS and still pass.

### E — Events/callbacks
- **Preconditions:** F1, F3 merged.
- **Deliverables:** `event[cached/not-cached]` implementation; detached-
  thread callback dispatch with try-catch isolation; `AuditSink` hook on
  OnChange.
- **Guarantees:** create/change/update fire events, read never does;
  callback exceptions never propagate to the caller thread; cached
  subscriptions receive the last value immediately.
- **Out of scope:** none of the serialization work (Track F).
- **Tests:**
  - Unit: cached vs. not-cached delivery semantics; callback exception
    isolation.
  - Integration: subscribe → mutate → assert callback fires with correct
    payload and, for `phi` fields, an audit record is emitted.
  - Acceptance gate: new functionality, no prior behavior to preserve —
    gate is 100% pass on its own new tests.

### F — Serialization unification (YAML + redaction)
- **Preconditions:** F2 merged.
- **Deliverables:** `YamlAdapter/`; unified `toString` path across
  JSON/XML/YAML; `phi` redaction applied uniformly per the architecture-doc
  safety-valve language.
- **Guarantees:** `toString` never crashes, never omits structure; `phi`
  values redacted by default in all three formats; the unredacted-output
  flag, when used, itself triggers an audit record.
- **Tests:**
  - Unit: redaction present in all three formats for `phi` fields.
  - Unit: unredacted flag reveals the real value AND emits an audit record.
  - Integration: round-trip a message with `phi` fields through all three
    formats; structure/keys always present, values redacted by default.
  - Acceptance gate: existing JSON/XML golden snapshots (14.5/14.6)
    unchanged for non-`phi` messages.

### I — sha256 registry / continuable process
- **Preconditions:** F1 merged. Run this right after Foundation, same
  session as Track L, before either fragments further into `main.py`.
- **Deliverables:** unique file/folder creation interface; per-file sha256
  + metadata registry; per-process and main registry files; resume logic.
- **Guarantees:** an interrupted pipeline run resumes from the last
  completed stage rather than restarting; a corrupted/tampered file is
  detected via sha256 mismatch and triggers recompute.
- **Tests:**
  - Unit: sha256 stored matches file; mismatch detected on corruption.
  - Integration: kill `main.py` mid-run at a known stage, rerun, confirm it
    resumes and the final output matches a clean, uninterrupted run
    byte-for-byte.
  - Acceptance gate: full pipeline output unchanged vs. F4 baseline when
    run without interruption (registry machinery has zero side effects on
    normal runs).

### L — Versioning/git integration
- **Preconditions:** F1 merged; same session as Track I, immediately after
  — shares registry version-stamp fields.
- **Deliverables:** fork-tracking metadata; version stamps feeding the
  registry's "associated version / calculated version" fields.
- **Guarantees:** version lineage is recoverable for any generated project;
  projects without git present degrade gracefully (no crash, no forced
  requirement).
- **Tests:**
  - Unit: version stamp matches actual git state.
  - Integration: fork a harpia project, regenerate, confirm lineage
    recorded and traceable back to the parent.
  - Acceptance gate: no-git environments still generate successfully.

### M — Process artifacts (SBOM, traceability matrix, jurisdiction docs)
- **Preconditions:** F1 merged. Benefits from, but doesn't hard-block on,
  Track I landing first.
- **Deliverables:** `ComplianceReport/` module emitting an SBOM
  (CycloneDX/SPDX), a traceability matrix (one code path, one set of
  evidence), and jurisdiction-selected doc templates (fda/eu_mdr/anvisa)
  that stamp that same evidence into whichever paperwork shell
  `jurisdiction[]` names.
- **Guarantees:** SBOM validates against its schema; every
  requirement-annotated construct produces a traceability row; output
  format correctly follows the selected jurisdiction's template.
- **Tests:**
  - Unit: SBOM schema validation; one matrix row per annotated construct.
  - Integration: full pipeline run on `HarpiaTest`, spot-check matrix rows
    against known `phi` fields and their Track A/E tests.
  - Acceptance gate: doc output differs correctly across the three
    jurisdiction templates for the *same* underlying evidence (same SBOM,
    same traceability matrix — only the document shell changes).

### N — Static/fuzz analysis CI
- **Preconditions:** none.
- **Deliverables:** CERT-ruleset static analysis job on generated output;
  fuzz harness for JSON/XML/SOAP parsers.
- **Guarantees:** CI fails on new static-analysis findings above an agreed
  severity; fuzz corpus runs N iterations with no crashes.
- **Tests:** the CI jobs *are* the test — "acceptance gate" here is a clean
  (or explicitly triaged) run against the current codebase before the job
  is considered live.

### J — Multi-language codegen (first target language)
- **Preconditions:** F1 merged (for any compliance-aware emitters).
- **Which language:** don't re-derive this — `plans/multi-language-targets.md`
  already did a real per-stage cost analysis (stages 0–6 + `.proto` emission
  are free for any language, since that's inherent to using protobuf as the
  IR; stages 8–14 are where real per-language cost lives) and recommends
  **Python**, with the explicit warning that it's "a multi-session effort in
  its own right, not a quick session." Read that doc before scoping this
  track further.
- **Deliverables:** Stage 8–14 emitters for one chosen target language,
  reusing `protoc`/`grpc`'s native multi-language message/stub generation
  instead of hand-rolling it.
- **Guarantees:** generated target-language project builds and runs a
  client/server demo mirroring the existing C++ one.
- **Out of scope:** the second and third languages — this track exists to
  prove the plugin-style split, not to ship all languages at once. Do
  **not** extrapolate the Python cost analysis to Rust/Node/Java ahead of
  time either (considered and rejected during this plan's 2026-08-18
  scoping session — see `plans/multi-language-targets.md`'s closing note):
  Python's per-stage costs lean on Python-specific facts (its protobuf
  JSON support, its reflection API shape, its DB/HTTP ecosystem) that don't
  transfer by analogy to languages with a different type system or no
  runtime reflection. Extract the general N-language seam only after a
  second real language exists to compare against C++ — same precedent as
  `Database/backends/` not being designed until Postgres was a real second
  case.
- **Tests:**
  - Unit: each emitter produces code that compiles/type-checks in the
    target language.
  - Integration: full generate → build → run demo, target language.
  - Acceptance gate: establishes its own golden-snapshot baseline (first
    of its kind — nothing prior to diff against).
