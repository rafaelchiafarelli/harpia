# Harpia → Medical-Device-Grade: Master Implementation Plan

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
| F4 | Golden-snapshot / regression baseline confirmed green before anything branches | `UnitTests/` | So every track has a clean starting point to diff against. |
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
| P | DDS transport adapter (real-time pub/sub, ASTM F2761/OpenICE-class bedside device bus) — new `dds` transport modifier value, `DdsAdapter/` module mirroring `ZmqAdapter/`'s shape, QoS derived from the existing critical/non-critical delivery-guarantee split in `harpia_sensitive_data_design_rules.md` §4 | new `DdsAdapter/` | F1, F3, F5 | Same session as Track Q — new session (5), not the Session-2 four rows, since it's net-new module footprint rather than hardening an existing one. |
| Q | IEEE 11073 SDC/BICEPS device-interop bindings — WS-Discovery + BICEPS participant model (MDS/VMD/Channel/Metric) layered on the existing MDPWS-compatible SOAP stack (Stage 11) | `Database/SoapAdapter.py`, `Database/WsdlAdapter.py`, new `SdcAdapter/` (scoping only this pass — see contract) | F1, F2 | Same session as Track P, after it. Scoping/design-doc deliverable only — do not treat as a green light to implement the full BICEPS state machine in one sitting. |
| R | HL7 FHIR façade — per-resource mapping (`.harpia` message → FHIR resource type + terminology binding), new REST surface emitted alongside Stage 12's existing generic REST endpoint, not replacing it | `Database/RestAdapter.py` (reads from, doesn't modify), new `FhirAdapter/` (scoping only this pass — see contract) | F1, F2 | Same session as Track P/Q, last. Design-doc deliverable this pass, same posture as Track Q. |
| E | Events/callbacks framework (`event[cached/not-cached]`, detached-thread callbacks) with `AuditSink` hooks at OnChange | `Logger/`, new `Callback/` module | F1, F3 | none directly, but logically depends on F3's interface shape |
| F | Serialization unification: add YAML pretty-print, close out the JSON/XML/YAML `toString` triad through one shared path, wire `phi` redaction into it | `JsonAdapter/`, `XmlAdapter/`, new `YamlAdapter/`, `Message/` toString templates | F2 | none |
| I | ~~sha256-registry / continuable-process machinery~~ **DONE, superseded — see 2026-08-23 update note above. Not a Session 4 task.** | n/a | n/a | n/a |
| L | Versioning/git integration (per-project fork tracking) | `ComplianceReport/` (Track M's module — decided 2026-08-23, was `Util/`/`main.py`) | F1, Track M's Session M.1 | **Decided 2026-08-23: folded into Track M's `ComplianceReport/`/SBOM output instead of a new registry/sidecar (Track I doesn't exist as a task). Coordinate with Track M — L waits on M.1.** |
| M | Process artifacts: SBOM, traceability matrix, jurisdiction-selected risk-file/doc templates (fda/eu_mdr/anvisa) — same underlying evidence, different paperwork shell | new `ComplianceReport/` module | F1 | Benefits from I landing first but doesn't hard-block on it. |
| N | Static/fuzz analysis CI (cppcheck/clang-tidy CERT ruleset on generated output, fuzz harness for JSON/XML/SOAP parsers) | `UnitTests/`, CI config only | none | Pure tooling, safe anywhere, anytime. |
| J | ~~Multi-language codegen (Java)~~ **DONE 2026-08-25 — see the detailed contract below.** Not a Session 4 task. | n/a | n/a | n/a |

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
**Update (2026-08-23): Track I dropped — see the top-of-doc update note.**
Track L (now blocked on its own open question, not on Track I — see
Track L's contract) → Track J / Track M / Track N, in any order — no
dependencies among them now that Track N no longer carries a
cross-variant parity diff (§0a dropped it, since there's only one code
path to test).

### Session 5 — Device Interoperability (new)
Track P → Track Q → Track R. Not one of the original four sessions — added later,
independently startable once Foundation (F1, F3, F5) is merged, same
precondition as Session 2's Track C. Runs Track P (DDS transport) first,
since Track Q's SOAP-based SDC work benefits from Track P's QoS/
delivery-guarantee mapping existing as a worked precedent for how a new
transport ties into the existing `phi`/`critical` schema-level modifiers,
though there's no hard file dependency between the two.

**Why this didn't fold into Session 2:** Track P/Q are net-new module
footprints (`DdsAdapter/`, `SdcAdapter/`), not hardening of an existing
one — Session 2's "keep C and B together so the credential model stays
consistent" rationale doesn't transfer, since Track P/Q don't touch the
gRPC/REST/SOAP credential gate Track C establishes. If Session 2 finishes
early, its session can pick up Track P as a next task rather than opening
a strictly separate fifth session — but keep P → Q sequential regardless
of which session executes them.

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

### P — DDS transport adapter (ASTM F2761/OpenICE-class bedside bus)
- **Preconditions:** F1, F3, F5 merged.
- **Why DDS, specifically:** ASTM F2761 (the ICE — Integrated Clinical
  Environment — standard) and its reference implementation, OpenICE, use
  OMG DDS as the interconnect for bedside device coordination (ventilator,
  infusion pump, patient monitor, etc. on one clinical network). Neither
  gRPC (Track C) nor ZMQ (Track B) is what a clinical-environment
  integrator building to that architecture will expect on the wire — DDS's
  data-centric, QoS-driven pub/sub model, not request/response, is the
  actual interoperability target here. This track doesn't replace ZMQ or
  gRPC; it's a third selectable transport for messages that need to cross
  into an ICE-class bus.
- **Grammar:** a new `dds` transport-modifier value, composable the same
  way `push`/`pull`/`event`/`stream` are today (§ process.md's access-
  modifier system) — a message picks `dds` when it needs to be published
  onto/read from a DDS bus, independent of whether it's also reachable via
  ZMQ or gRPC.
- **QoS mapping is not a new design decision — it's already implied by
  existing rules.** `harpia_sensitive_data_design_rules.md` §4 already
  splits delivery guarantee into two categories per message *type*
  (ordered/complete vs. latest-value-only), chosen at the schema level,
  never inferred at runtime. That split maps directly onto DDS QoS
  policies:
  - **4a (ordered/complete, `critical`-style)** → `RELIABILITY=RELIABLE`,
    `HISTORY=KEEP_ALL` (bounded by the same queue-depth reasoning §4a
    already specifies — DDS's `resource_limits` is the mechanism, not a
    new concept), `DURABILITY=TRANSIENT_LOCAL` if late-joining subscribers
    need catch-up (open question, same status as §4a's own open items —
    decide per use case, don't default it on).
  - **4b (latest-value-only)** → `RELIABILITY=BEST_EFFORT`,
    `HISTORY=KEEP_LAST(1)` — this is DDS's native double-buffer-mailbox
    equivalent to §4b's mechanism, not an approximation of it.
  - **Deadline QoS** (DDS can detect a publisher missing its expected
    period) is a genuinely new capability beyond what §4 currently
    specifies — flag as an **open question for this track**, not a
    decision made here: does a periodic vitals stream (e.g. heart rate)
    want a schema-level `deadline[ms]` modifier that DDS enforces and
    `AuditSink` records a violation of? Don't invent the modifier name or
    semantics without a domain-expert pass, same caution
    `harpia_sensitive_data_design_rules.md` uses for its own open items.
- **DDS Security parity with Track B/C:** the OMG DDS-Security spec
  (authentication, access-control, and encryption plugins) is this
  track's analogue of Track C's mTLS and Track B's CURVE — compiled in via
  the F5 `CryptoBackend` seam, one selection per project driven by
  `risk_class`/`topology`, not per jurisdiction (§0a). Plaintext/
  unauthenticated DDS refused by default when the compliance profile
  requires it, same rule as Track B/C. **Out of scope, by decision, not an
  open item:** LGPD Art. 33 (international transfer) and Art. 11 §4 (no
  sharing sensitive health data between controllers for economic
  advantage) constrain where a `phi`-tagged message is allowed to go once
  it leaves the device's own custody — but *which* endpoints a deployment
  may reach is a network-topology/deployment-configuration fact, not
  something Harpia's generated code can know or enforce at compile time or
  runtime. Harpia guarantees the transport is authenticated/encrypted and
  the `phi` access is audited (this contract, Track A/E's pattern); it
  does not and will not police the legal status of the recipient on the
  other end of a DDS subscription, a gRPC peer, or a FHIR client. That
  determination belongs to the integrator's deployment topology and legal
  review, not to a schema-level modifier or a generated runtime check.
- **Deliverables:** new `DdsAdapter/` module (mirrors `ZmqAdapter/`'s
  shape: `DdsAdapter.py` filtering messages by the `dds` modifier,
  `templates/` for publisher/subscriber/QoS-profile fragments); a vendored
  or `third_party/`-linked DDS implementation (e.g. Eclipse Cyclone DDS —
  exact vendor TBD, prove the interface is real before picking one,
  same posture as Track O's KMS reference adapter); DDS-Security wiring
  consuming F5; `dds` grammar support in `LexicalAnalizer/`/`Message/`.
- **Guarantees:** a message tagged `dds` + non-`critical` gets
  `BEST_EFFORT`/`KEEP_LAST(1)` QoS; a message tagged `dds` + `critical`
  gets `RELIABLE`/`KEEP_ALL` QoS with the same overflow-rotation-not-drop
  behavior §4a mandates for its ZMQ/queue equivalent; a `phi` field
  crossing the DDS transport triggers the same `AuditSink` call pattern
  Track A/E already establish for DB and event delivery — the transport
  changes, the audit obligation doesn't.
- **Out of scope:** the full BICEPS/MDPWS device-interop semantic layer —
  that's Track Q. This track is transport/QoS only, same boundary Track B
  keeps against Track C.
- **Tests:**
  - Unit: `critical`/non-`critical` messages map to the correct QoS
    profile; `dds` composes correctly with `phi`, `optional`, `repeteable`
    per existing modifier-composition tests.
  - Integration: a client/server DDS demo (mirroring the existing ZMQ
    demo in `UnitTests/test_demo.py`) — publish a `critical` and a
    non-`critical` message, confirm delivery semantics differ as
    specified (drop/overwrite vs. queue-and-retry) under a simulated
    transient network gap.
  - Integration: `phi` field over DDS emits exactly one `AuditSink`
    record per publish, matching Track A/E's pattern.
  - Acceptance gate: existing ZMQ/gRPC demo tests unaffected — `dds` is
    additive, not a replacement for either.

### Q — IEEE 11073 SDC/BICEPS device-interop bindings (scoping only)
- **Preconditions:** F1, F2 merged. Same session as Track P, after it.
- **Explicitly scoped as a design/scoping deliverable this pass, not a
  full implementation** — same posture the master plan already takes with
  Track J (multi-language codegen): prove the seam is real with a
  concrete design before committing to build the whole thing. IEEE 11073
  SDC (ISO/IEEE 11073-10700 series: BICEPS + MDPWS) is a substantially
  larger semantic lift than Track P's transport/QoS work — it defines a
  whole participant/data model (MDS → VMD → Channel → Metric/Alert/
  Context hierarchy), not just a wire protocol.
- **Why this leans on Track C's Stage 11 SOAP work rather than starting
  cold:** MDPWS (the SDC transport binding) is SOAP-over-HTTP with
  WS-Discovery for zero-config peer discovery. Harpia's generator already
  emits WSDL + SOAP endpoints (`Database/SoapAdapter.py`,
  `Database/WsdlAdapter.py`, Stage 11) gated by the same credential model
  Track C is hardening. The realistic scope for this track is: (a) add a
  WS-Discovery probe/resolve responder (UDP multicast, not currently
  emitted anywhere in the pipeline) alongside the existing SOAP endpoint,
  and (b) design — not yet implement — how a `.harpia` message maps onto
  BICEPS's Metric/Alert/Context categories.
- **Open question this track exists to answer, not assume:** whether the
  existing access-modifier vocabulary (`stream`, `event[cached/not-
  cached]`, `pull`, `push`, `pushpull`) maps cleanly onto BICEPS's
  Metric/Alert/Context split, or whether that forces a new modifier
  the way `phi`/`critical` were added for their own concerns. A first
  guess — `event`-modified messages ≈ BICEPS Metric reports (periodic
  value + validity state), `critical event` ≈ Alert (matches Track P's
  QoS treatment naturally), and something not yet in the grammar ≈
  Context (rarely-changing patient/location association) — is a
  **hypothesis to validate with a domain-expert/regulatory-affairs
  pass**, not a decision made by this contract. Do not lock grammar
  changes from this guess without that validation, per the same
  discipline `harpia_sensitive_data_design_rules.md` §7 already applies
  to its own open items.
- **Deliverables (this pass):** a written design doc (new
  `Initiatives/medical_devices/epics/thread-5-device-interop/histories/sdc-biceps/sdc_biceps_design.md`, follow-on to this
  contract) covering the Metric/Alert/Context mapping question above; a
  working WS-Discovery probe/resolve responder as a standalone,
  demonstrable piece (independent of the mapping question, since
  discovery doesn't require the data-model decision to be settled first).
- **Out of scope this pass:** the full BICEPS state machine, MDS/VMD/
  Channel participant model implementation, and any SDC-specific
  `SdcAdapter/` code generation beyond the WS-Discovery responder — these
  become their own follow-on track(s) once the design doc's open question
  is resolved.
- **Tests:**
  - Unit: WS-Discovery probe/resolve responder answers a multicast probe
    correctly (matches the participant's declared type/scope).
  - Integration: a generic SDC-aware client (or a minimal test harness
    mimicking one) discovers a Harpia-generated endpoint via WS-Discovery
    and successfully opens the existing SOAP/MDPWS-compatible connection.
  - Acceptance gate: existing Stage 11 SOAP tests (14.8/14.9) unaffected —
    WS-Discovery is additive to the existing SOAP endpoint, not a
    replacement for it.

### R — HL7 FHIR façade (scoping only)
- **Preconditions:** F1, F2 merged. Same session as Track P/Q, last —
  benefits from Track Q's mapping-question precedent (schema field →
  external standard vocabulary) but has no file dependency on it.
- **Corrected framing (2026-08-21):** an earlier pass dismissed FHIR as
  "orthogonal — system-to-system, not device IPC." That's wrong on the
  mechanism: FHIR's RESTful convention (verbs, JSON/XML, content
  negotiation) is exactly what Stage 12 already emits. The actual gap is
  FHIR's **fixed resource vocabulary and terminology bindings**
  (`Patient`, `Observation`, `DeviceMetric`, fields coded against
  LOINC/SNOMED/UCUM rather than free-form) — nothing a schema-driven
  generator produces automatically, since `.harpia` intentionally lets
  the author define arbitrary message shapes.
- **Design doc (2026-08-21, full scoping conversation captured) — merged
  2026-08-23 into**
  `Initiatives/medical_devices/epics/thread-5-device-interop/histories/fhir-facade/track-r-fhir-facade.md`
  (the original standalone `fhir_mapping_design.md` is deleted; that
  thread file is now the canonical source). Decisions settled enough to
  build against, and open questions still needing resolution, are both
  there — summary below, don't duplicate detail here.
- **What this track actually is:** a translation façade sitting beside
  the existing adapters, never touching `ProtoFile/FileCreator.py`,
  `ProtoCompiler.py`, or `GrpcCompiler.py` — same relationship
  `JsonAdapter`/`SoapAdapter.py`/`RestAdapter.py` already have to the
  compiled message. A `.harpia` author opts a message into a FHIR
  resource mapping (two-level: message → resource type, field → element
  — explicit only, **never inferred from field name/type**, same
  discipline as `phi`/`critical`); the generator emits a second,
  FHIR-conformant REST endpoint alongside the existing generic one
  (Stage 12/`RestAdapter.py` read from, not modified).
- **Settled design points (see design doc for full reasoning):**
  - Generated code is complete for declared mappings, never a stub —
    same guarantee `to_json`/`from_json` already give. Unmapped fields
    are either omitted (valid FHIR) or carried as a Harpia-namespaced
    `extension` — never fabricated.
  - FHIR is a full two-way REST CRUD surface, not one-directional. Two
    consequences: (a) Harpia must generate a `CapabilityStatement`
    listing only the resource types actually mapped — never implying
    support for the full ~150-type catalog; (b) **read access needs the
    same RBAC/audit gating Track C puts on writes** — a `phi`-tagged
    `GET` is processing too, not a lesser case.
  - Composite `critical` messages spanning multiple resources use
    FHIR's native `Reference`/`Bundle` mechanisms — a per-message
    judgment call by the schema author, not a Harpia default.
  - Cross-message PHI identity (e.g. two `critical` messages both
    carrying `patient_id`) is **never linked by name match** — that's
    the same forbidden inference as auto-detecting mapping from field
    names. Requires an explicit identity-tag declaration, resolved via
    FHIR's `identifier` (system+value) element and the target server's
    own conditional-create/match — Harpia's generator stays stateless
    per message compile.
  - LGPD (Brazil): no resource type conflicts with LGPD outright: this is a
    legal-basis-and-recipient question (Art. 11, closed exception list,
    §4's anti-sharing-for-economic-advantage clause), not a schema
    question. Each resource mapping will need an explicit legal-basis +
    recipient declaration once the grammar is designed — not legal
    advice, needs counsel/DPO sign-off.
- **Deliverables (this pass, scoping only — same posture as Track Q):**
  - The design above (merged 2026-08-23 into `track-r-fhir-facade.md`,
    see the note at the top of this contract) — done, captures the
    above; grammar syntax itself still not committed (see open
    questions).
  - A worked example: one existing message type (e.g. the
    `HeartRateReading` example from `harpia_sensitive_data_design_rules.md`)
    mapped by hand to a FHIR `Observation` with a real LOINC code, to
    prove the mapping is expressible before generalizing it into a
    grammar feature. **Not yet done — next concrete step.**
- **Open questions (full list + rationale in the design doc §"Open
  questions"):** terminology-code binding static-vs-dynamic; resource
  scope for first pass (`Patient`/`MedicationRequest` in or out);
  `meta.security` vs. custom extension for `phi`/legal-basis metadata;
  `modifierExtension` criteria; composition default (if any); `identifier
  .system` minting scope (project/deployment/org — get this wrong and
  two Harpia deployments could collide, recreating the exact problem the
  mechanism exists to prevent); legal-basis/recipient declaration
  grammar (needs LGPD counsel before syntax is locked); whether Track
  C's three-role RBAC is granular enough for per-resource FHIR read
  gating.
- **Out of scope this pass:** any generated `FhirAdapter/` code, `Bundle`/
  transaction semantics, FHIR search-parameter query support, the
  `CapabilityStatement` endpoint itself, full implementation-guide/
  profile conformance certification, the `identifier` mechanism's actual
  DSL syntax — all follow-on work once the design doc's open questions
  are resolved, same discipline as Track Q.
- **Tests:**
  - Integration (design-validation, not generated code): the hand-mapped
    `Observation` example validates against HL7's published FHIR
    resource schema (e.g. via a public FHIR validator) — proves the
    target shape is reachable from Harpia's data model at all, before
    any codegen is built.
  - Acceptance gate: none yet — this pass produces a doc + one manual
    example, not shipped code; the real acceptance gate belongs to the
    follow-on implementation track.

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

### I — ~~sha256 registry / continuable process~~ DONE — superseded, not a task

**Correction (2026-08-23):** everything below this line is the original
scoping, kept for history — do not build it. The problem it was scoped to
solve (interrupt/crash recovery) shipped 2026-08-19, via a mechanism that
makes every deliverable/test below moot:

- **What actually shipped, instead:** every generated file goes through
  `Util.util.write_if_different`/`copy_if_different` — content comparison
  (not a marker or sha256), atomic same-directory temp-file + `os.replace`.
  A process killed mid-write never leaves a truncated file at the
  destination; rerunning the whole pipeline after a kill reproduces
  identical content for already-correct files (skipped, no wasted write)
  and completes whatever didn't finish — self-resuming with no registry,
  no `.sha256` sidecars, no start/finish markers, no per-process/main
  registry files. See `Util/CLAUDE.md` for the full account of why the
  registry design was dropped in favor of this.
- **Real fallout, not resolved by this correction:** Track L below was
  scoped to depend on this track — "shares registry version-stamp
  fields" — because version metadata was meant to live in the registry
  this track would have built. That registry doesn't exist. See Track L's
  contract for the resulting open question.

Original scoping (do not build):
- ~~**Preconditions:** F1 merged. Run this right after Foundation, same
  session as Track L, before either fragments further into `main.py`.~~
- ~~**Deliverables:** unique file/folder creation interface; per-file sha256
  + metadata registry; per-process and main registry files; resume logic.~~
- ~~**Guarantees:** an interrupted pipeline run resumes from the last
  completed stage rather than restarting; a corrupted/tampered file is
  detected via sha256 mismatch and triggers recompute.~~
- ~~**Tests:**~~
  - ~~Unit: sha256 stored matches file; mismatch detected on corruption.~~
  - ~~Integration: kill `main.py` mid-run at a known stage, rerun, confirm it
    resumes and the final output matches a clean, uninterrupted run
    byte-for-byte.~~
  - ~~Acceptance gate: full pipeline output unchanged vs. F4 baseline when
    run without interruption (registry machinery has zero side effects on
    normal runs).~~

### L — Versioning/git integration
- **Decided 2026-08-23:** this track's original deliverable was "version
  stamps feeding the registry's 'associated version / calculated
  version' fields" — but that registry was Track I's, and Track I never
  got built (superseded by a different mechanism that has no registry at
  all — see Track I's contract above). Resolved by folding version
  stamps into Track M's `ComplianceReport/`/SBOM output instead of a new
  mechanism — Track M already has a per-project artifact module; version
  lineage is one more field in something it already emits. Full session
  breakdown (L.1/L.2) in
  `Initiatives/medical_devices/epics/thread-4-platform-infra/histories/versioning/track-l-versioning.md`.
- **Preconditions (updated):** F1 merged; Track M's Session M.1 merged
  (the `ComplianceReport/` module must exist to extend) — replaces the
  old "same session as Track I" coupling.
- **Deliverables (updated):** fork-tracking metadata; version stamps
  emitted as fields within Track M's `ComplianceReport/`/SBOM output.
- **Guarantees:** version lineage is recoverable for any generated project;
  projects without git present degrade gracefully (no crash, no forced
  requirement).
- **Tests:**
  - Unit: version stamp matches actual git state.
  - Integration: fork a harpia project, regenerate, confirm lineage
    recorded and traceable back to the parent.
  - Acceptance gate: no-git environments still generate successfully.

### M — Process artifacts (SBOM, traceability matrix, jurisdiction docs)
- **Preconditions:** F1 merged. ~~Benefits from, but doesn't hard-block
  on, Track I landing first.~~ **(2026-08-23: Track I doesn't exist as a
  task anymore — see the top-of-doc update note. No dependency to
  benefit from.)**
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

**Shipped 2026-08-25, and no longer medical-devices-specific work.**
Restructured 2026-08-23 into its own standalone plan,
`Initiatives/multi-language-targets/` (Java as a full generation target,
symmetric with C++, plus on-device Android consumption verification —
27 sessions). That plan has since shipped in full and, per this repo's
convention, been **removed from `Initiatives/`** — its design rationale
now lives in the code's own `CLAUDE.md` files (`GradleAdapter/CLAUDE.md`
for the build-time-codegen decision, `JavaJsonAdapter/CLAUDE.md` for the
full-protobuf-runtime-vs-`javalite` decision, `JavaZmqAdapter/CLAUDE.md`
for the JeroMQ/CURVE story) and in `HarpiaTest/app_example/android_consumer/README.md`
for the Android verification account. Selection history, preserved here
since it explains sequencing rather than implementation: Python was the
original per-stage-cost recommendation (2026-08-11), but a concrete
business need — an existing Android fleet wanting harpia-generated Java
code — overrode that in a 2026-08-22 addendum. Python is still next in
line as language #3, not dropped.

- **Conditional follow-on, not yet scoped:** if/when this fleet's shipped
  Java target needs to be compliance-aware (`risk_class`/`phi`-respecting
  like the C++ target, gated on F1), that's a new, separate contract to
  write when it's actually needed — nothing here to link to yet.
- **Tests (as delivered):** each stage's generated Java code
  compiles/type-checks; a full generate → build → run demo passed for the
  desktop/server shape; the Android on-device acceptance gate (all four
  `connectedAndroidTest` methods across message classes, JSON, gRPC
  client, and JeroMQ ZMQ) passed for real on a headless emulator — see
  `HarpiaTest/app_example/android_consumer/README.md`'s verification-status section.
