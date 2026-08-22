# Session 4 — Platform Infra & Expansion

Covers Track I → Track L (sequential, share files) → Track J / Track M /
Track N (any order, no dependency among them or on any other session).

**Update (2026-08-22):** Reconciled against `harpia_medical_master_plan.md`
§0a — jurisdiction is not a code-generation axis; `risk_class` is the
single project-wide hardening floor, not a per-jurisdiction fan-out. Track
N's feature-parity diff (the old cross-session convergence point this file
used to gate on) is dropped entirely: with one code path, there's nothing
to diff. Track N is now static/fuzz analysis only, same as Track J/M —
genuinely no cross-session dependency left in this session.

---

## Preconditions

Foundation (F1–F5) merged to `main`. Confirm before starting:
- `ComplianceContext` is threaded through `main.py` and every stage.
- A tagged F4 regression baseline exists.

---

## Execution order

1. **Track I**, then **Track L** immediately after, same session — both
   touch `main.py` orchestration and share the registry's version-stamp
   fields.
2. **Track J, Track M, Track N** — no dependencies on each other, on I/L,
   or on any other session (§0a dropped Track N's old cross-session
   parity-diff dependency) — run in whatever order suits.

### Squaring the numbers
At kickoff, Sessions 1 (needs two concurrent sub-sessions for Track O and
Track H), 2, and 3 already account for all four available sessions —
Session 4 doesn't get a dedicated one immediately. Whichever of Track O
or Track H (Session 1) finishes first should pick up a task from this
session as filler while waiting on the other. Once Track O and Track H
both merge, that filler session redirects back to Session 1's Track A →
Track K, and whatever Session-4 task was mid-flight either pauses or gets
picked up by the next session that frees up.

---

## Contracts

### Track I — sha256 registry / continuable process
- **Depends on:** F1.
- **Deliverables:** unique file/folder creation interface; per-file
  sha256 + metadata registry; per-process and main registry files; resume
  logic reading start/finish markers.
- **Guarantees:** an interrupted pipeline run resumes from the last
  completed stage rather than restarting; a corrupted/tampered file is
  detected via sha256 mismatch and triggers recompute.
- **Tests:**
  - Unit: sha256 stored matches file; mismatch detected on corruption.
  - Integration: kill `main.py` mid-run at a known stage, rerun, confirm
    it resumes and the final output matches a clean, uninterrupted run
    byte-for-byte.
  - Acceptance gate: full pipeline output unchanged vs. F4 baseline when
    run without interruption.

### Track L — Versioning/git integration
- **Depends on:** F1, Track I (same session, immediately after).
- **Deliverables:** fork-tracking metadata; version stamps feeding the
  registry's "associated version / calculated version" fields.
- **Guarantees:** version lineage is recoverable for any generated
  project; projects without git present degrade gracefully.
- **Tests:**
  - Unit: version stamp matches actual git state.
  - Integration: fork a harpia project, regenerate, confirm lineage
    recorded and traceable back to the parent.
  - Acceptance gate: no-git environments still generate successfully.

### Track M — Process artifacts (SBOM, traceability matrix, jurisdiction docs)
- **Depends on:** F1. Benefits from, but doesn't hard-block on, Track I
  landing first.
- **Note:** this is the one track where `jurisdiction[]` actually drives
  different output — everywhere else it's inert past F1 (§0a).
- **Deliverables:** `ComplianceReport/` module emitting an SBOM
  (CycloneDX/SPDX), a traceability matrix, and jurisdiction-selected doc
  templates (fda/eu_mdr/anvisa) — same underlying evidence, different
  paperwork shell.
- **Guarantees:** SBOM validates against its schema; every requirement-
  annotated construct produces a traceability row; output format
  correctly follows the selected jurisdiction's template.
- **Tests:**
  - Unit: SBOM schema validation; one matrix row per annotated construct.
  - Integration: full pipeline run on `HarpiaTest`, spot-check matrix
    rows against known `phi` fields and their Track A/E tests.
  - Acceptance gate: doc output differs correctly across the three
    jurisdiction templates for the *same* underlying evidence (same SBOM,
    same traceability rows — only the template shell changes).

### Track N — Static/fuzz analysis CI
- **Depends on:** none. No cross-variant parity gate — that job was
  dropped entirely per `harpia_medical_master_plan.md` §0a (one
  project-wide `risk_class` floor, not per-jurisdiction builds, so there
  are no build variants left to diff).
- **Deliverables:** CERT-ruleset static analysis job on generated output;
  fuzz harness for JSON/XML/SOAP parsers.
- **Guarantees:** CI fails on new static-analysis findings above an
  agreed severity; fuzz corpus runs N iterations with no crashes.
- **Tests:** the CI jobs *are* the test — "acceptance gate" is a clean
  (or explicitly triaged) run against the current codebase before the job
  is considered live.

### Track J — Multi-language codegen (first target language)
- **Depends on:** F1 (for any compliance-aware emitters).
- **Update (2026-08-18) — which language, and a guardrail:**
  `plans/multi-language-targets.md` already did the real per-stage cost
  analysis and recommends **Python** — don't re-derive this. It also
  explicitly warns this is "a multi-session effort in its own right, not a
  quick session," since stages 8–14 need a genuinely different runtime
  library per language, not just a new template. Separately: extrapolating
  that Python-specific analysis onto Rust/Node/Java was raised and
  rejected during this same scoping session — Python's per-stage costs
  lean on Python-specific facts (its protobuf JSON support, its reflection
  API shape, its DB/HTTP ecosystem) that don't transfer to a language with
  a different type system or no runtime reflection. See
  `plans/multi-language-targets.md`'s closing note for the full reasoning
  (same precedent as `Database/backends/` waiting for a real second case
  before the seam was designed).
- **Deliverables:** Stage 8–14 emitters for one chosen target language —
  reuse `protoc`/`grpc`'s native multi-language message/stub generation
  for Stages 0–7 instead of reinventing it; only Stages 8–14 (DB/DAO,
  JSON/XML/SOAP/REST, ZMQ, auth, audit) need per-language emitters.
- **Guarantees:** generated target-language project builds and runs a
  client/server demo mirroring the existing C++ one.
- **Out of scope:** the second and third languages — this track proves
  the plugin-style split, not ship all languages at once. Also out of
  scope: any speculative Rust/Node/Java scoping (see update note above).
- **Tests:**
  - Unit: each emitter produces code that compiles/type-checks in the
    target language.
  - Integration: full generate → build → run demo, target language.
  - Acceptance gate: establishes its own golden-snapshot baseline (first
    of its kind).

---

## Definition of done (applies to every track above)

- Unit tests for every new construct/behavior introduced.
- Integration test covering end-to-end behavior in a realistic path.
- Full F4 regression baseline still passes.
- Track M is the consumer of every other track's `ComplianceReport/`
  notes — check those notes actually landed before considering Track M
  "done."

## Watch for

- Nothing cross-session left to gate on here — Track N's old
  feature-parity diff (which used to require Sessions 1 and 2 to land
  jurisdiction build variants first) was dropped entirely per
  `harpia_medical_master_plan.md` §0a. All of Track I/L/J/M/N is now
  genuinely self-contained within this session.
