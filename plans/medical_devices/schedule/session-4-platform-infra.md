# Session 4 — Platform Infra & Expansion

Covers Track I → Track L (sequential, share files) → Track J / Track M /
Track N's static-analysis half (any order) → Track N's feature-parity
diff (last, cross-session dependency).

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
2. **Track J, Track M, Track N's static/fuzz half** — no dependencies on
   each other or on I/L, run in whatever order suits.
3. **Track N's feature-parity diff — last, and gated on other sessions.**
   This needs compile-time jurisdiction variants from Track O/A (Session
   1) and Track C (Session 2) to exist before it has anything to diff.
   Don't activate it early — check with those sessions first.

**If this session starts before Sessions 1 or 2 have produced compile-time
variants** (likely, since this session doesn't get a dedicated slot until
one of Session 1's parallel tracks frees up — see "Squaring the numbers"
below): work Track I → L → J/M/N-static in the meantime, and hold the
parity-gate activation for whenever Session 1 and Session 2 signal
they're ready.

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
- **Deliverables:** `ComplianceReport/` module emitting an SBOM
  (CycloneDX/SPDX), a traceability matrix, and jurisdiction-forked doc
  templates (fda/eu_mdr/anvisa).
- **Guarantees:** SBOM validates against its schema; every requirement-
  annotated construct produces a traceability row; output format
  correctly follows the selected jurisdiction's template.
- **Tests:**
  - Unit: SBOM schema validation; one matrix row per annotated construct.
  - Integration: full pipeline run on `HarpiaTest`, spot-check matrix
    rows against known `phi` fields and their Track A/E tests.
  - Acceptance gate: doc output differs correctly across the three
    jurisdiction templates for the same underlying data.

### Track N — Static/fuzz analysis CI + feature-parity gate
- **Depends on:** none for the static/fuzz half. The feature-parity diff
  job needs compile-time jurisdiction variants from Track O/A (Session 1)
  and Track C (Session 2) — activate last.
- **Deliverables:** CERT-ruleset static analysis job on generated output;
  fuzz harness for JSON/XML/SOAP parsers; cross-variant feature-parity
  diff.
- **Guarantees:** CI fails on new static-analysis findings above an
  agreed severity; fuzz corpus runs N iterations with no crashes; parity
  diff fails the build if jurisdiction variants diverge outside
  designated strategy classes (audit recording, retention, residency,
  crypto module linkage).
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

- Don't merge/activate Track N's feature-parity diff job until Session 1
  and Session 2 both confirm their compile-time jurisdiction variants
  exist — it has nothing meaningful to compare before then, and an early
  activation will just be a permanently-failing or meaningless CI job.
