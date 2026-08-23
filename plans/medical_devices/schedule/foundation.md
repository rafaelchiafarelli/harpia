# Session 0 — Foundation

Serial. Single session. Must merge to `main` before any other session
(1–4) starts on any repo copy. This is the one synchronization point
everyone else waits on.

**Update (2026-08-22):** Reconciled against `harpia_medical_master_plan.md`
§0a (decided 2026-08-19, `harpia_sensitive_data_design_rules.md` §6/§6a) —
jurisdiction is not a code-generation axis. F1/F3/F5 below were still
describing "one compile-time build variant per jurisdiction"; corrected
throughout. The actual mechanism: `risk_class` is the single project-wide
hardening floor (no per-jurisdiction fan-out); `jurisdiction[]` is inert
for codegen, read only by Track M to pick a paperwork template. Track N's
cross-variant feature-parity diff is dropped entirely — one code path,
nothing to diff.

---

## Required reading — design rules reference (added 2026-08-23)

[`harpia_sensitive_data_design_rules.md`](../harpia_sensitive_data_design_rules.md)
is the working-draft rulebook for how `phi`/`critical` (and every
sensitive-data concern layered on top of them) actually behave — the
confidentiality-vs-criticality axis split (§0), delivery-guarantee rules
(§4/§4a/§4b), and the jurisdiction/`risk_class` decisions (§6/§6a) this
file's own F1/F3/F5 already build on. It isn't merged into this file or
any single track, on purpose: Foundation (F2 here), Track A, Track C,
Track F, Track P, and this doc's own §0a-equivalent (Foundation doesn't
have one, but downstream `harpia_medical_master_plan.md` §0a does) all
cite it by section number, and merging it into one place would break
every one of those citations. Read it before starting F2 specifically —
`phi`'s grammar landing point is defined here, that doc is where the
*rules* `phi` has to satisfy are worked out.

---

## Ground rules (apply to every session, not just this one)

1. Foundation lands first, alone, before anything else branches — every
   later track depends on the `ComplianceContext` object and the `phi`
   DSL tag existing.
2. One track = one module footprint, wherever possible. Where two tracks
   must share files, that's flagged explicitly as "Coordinate with."
3. Interfaces before implementations. `AuditSink` (and `KeyProvider`,
   `CryptoBackend` once built) are defined as stubs here in Foundation;
   downstream tracks wire their own calls to the interface independently.
4. Branch naming: `track-<ID>-<short-name>`, e.g. `track-C-transport-mtls`.
5. Merge order matters more than merge speed. A track marked "coordinate
   with X" merges *after* X, even if it finishes first.
6. **Doxygen doc-comments are part of the deliverable, not a follow-up
   (added 2026-08-23).** Any session/track that adds or modifies a
   consumer-facing template/adapter — anything that renders a header a
   harpia *consumer* `#include`s, not this repo's own internal code —
   must emit or update accurate Doxygen doc-comments for exactly what it
   touched, in that same session, not deferred to a separate pass.
   "Accurate" means: reflects the real pitfall/behavior for a consumer,
   not generic boilerplate — see `plans/doxygen-generation.md`'s pitfall
   table for the standard and its own worked examples, and add a new row
   there when a session's work introduces a pitfall not already listed,
   so the table doesn't go stale either. F6 below is the one-time
   plumbing (Doxyfile, CMake target, mainpage) this rule builds on top
   of — F6 doesn't do the per-template work itself, every later track
   owns that for its own templates.

---

## What this session delivers

| ID | Task | Touches | Notes |
|---|---|---|---|
| F1 | `ComplianceContext`: parse `project.harpia.yaml` (`risk_class`, `topology`, `phi_handling`, `jurisdiction[]` — paperwork routing only), thread it through `main.py` and every stage entry point | `main.py`, every `Stage*` entry signature | Highest blast radius in the whole plan. Fail-safe default (strictest settings) when unset/ambiguous. `risk_class` is the single project-wide hardening floor — no per-jurisdiction build variants, no fan-out (§0a). `jurisdiction[]` has zero effect on generated code; it only feeds Track M's doc-template selection. |
| F2 | `phi` (sensitive-field) modifier in the grammar + AST | `LexicalAnalizer/`, `Message/` | Needed before DB encryption, redacted `toString`, or audit-on-access can be built. Sensitivity is a **per-field** modifier, same category as `optional`/`required`/`unique` — never a whole-message property. |
| F3 | `AuditSink` interface — abstract/no-op stub only, no implementation yet | new `Compliance/` module | Real implementations happen in Track A (DB) and Track C (comm), independently. One implementation per project, gated by `risk_class`, not per jurisdiction (§0a). Build the stub already shaped for that. |
| F4 | Golden-snapshot / regression baseline confirmed green before anything branches | `tests/` | Every later track's "acceptance gate" diffs against this. |
| F5 | `CryptoBackend` selection point: compile-time seam choosing which underlying crypto module gets linked (e.g. standard vs. FIPS-validated OpenSSL) | new `Crypto/backend.py` (or build-flag/CMake option) | Both Track O (key-wrap/envelope-encryption) and Track C (TLS stack) must consume this, not each pick their own — prevents silent drift onto different crypto modules. One selection per project, driven by `risk_class`/`topology`, not per jurisdiction (§0a). |
| F6 | Doxygen infrastructure (added 2026-08-23): `Doxyfile` + CMake `doxygen` target; `@mainpage`/`USE_MDFILE_AS_MAINPAGE` pointed at a landing page assembled from `USAGE.md` (§4/§6/§11) | new `Doxyfile`, CMake target | One-time plumbing only — see `plans/doxygen-generation.md` §2. The *ongoing* per-template doc-comment discipline is Ground Rule 6 above, not a Foundation task: every later track owns keeping its own templates' comments accurate, this just builds the machinery that displays them. |

**Exit criterion:** F1–F6 merged to `main`, all existing tests green.

---

## Contracts

### F1 — ComplianceContext plumbing
- **Deliverables:** `Compliance/context.py` defining
  `ComplianceContext{risk_class, topology, phi_handling, jurisdiction[]}`;
  `project.harpia.yaml` parser; `main.py` and every `Stage*` entry point
  updated to receive it.
- **Guarantees after merge:** every stage has access to the active
  compliance profile; an invalid/unknown enum value is a hard error at
  generation start, never silently ignored; missing config defaults to the
  strictest profile with a logged warning; `risk_class` is the project-
  wide hardened floor — never a per-jurisdiction fan-out (§0a);
  `jurisdiction[]` is inert for codegen, read only by Track M.
- **Out of scope:** no jurisdiction-specific *code behavior* — by design,
  per §0a, there isn't any; plumbing only.
- **Tests:**
  - Unit: valid config parses correctly; missing file → strictest default;
    invalid enum value → hard error.
  - Integration: run the full pipeline against `HarpiaTest/test.harpia`
    with a compliance config present; confirm every stage received the
    context (e.g. a per-stage smoke marker).
  - Acceptance gate: F4 baseline unaffected when no config file is present.

### F2 — `phi` field modifier
- **Deliverables:** grammar + AST support for `phi` in
  `LexicalAnalizer/`/`Message/`; `field.is_phi` flag available to every
  later stage.
- **Guarantees:** fields without `phi` behave exactly as before, byte-for-
  byte; `phi` composes correctly with existing modifiers.
- **Out of scope:** no encryption, redaction, or audit logic — flag only.
- **Tests:**
  - Unit: parse messages with/without `phi`, alone and combined with other
    modifiers; confirm AST flags.
  - Integration: Stages 0–6 on a `.harpia` file with `phi` fields produce a
    clean `.proto`.
  - Acceptance gate: existing snapshot tests for non-`phi` messages
    unchanged.

### F3 — AuditSink interface (stub)
- **Deliverables:** abstract `AuditSink` interface + `NoOpAuditSink`
  default implementation; documented injection point for downstream tracks.
- **Guarantees:** interface compiles and instantiates standalone; no-op
  implementation has zero side effects.
- **Out of scope:** the real, tamper-evident implementation — built once
  per project, gated by `risk_class`, not per jurisdiction (§0a).
- **Tests:**
  - Unit: `NoOpAuditSink.record()` called, asserts no side effect, no crash.
  - Integration: instantiate and inject into a dummy generated class,
    confirm no build/runtime error.

### F4 — Regression baseline
- **Deliverables:** tagged, CI-recorded green baseline of the existing
  test suite.
- **Guarantees:** every subsequent track's acceptance gate refers back to
  this exact baseline.

### F5 — CryptoBackend selection point
- **Deliverables:** a single compile-time seam (build flag/CMake option),
  driven by `risk_class`/`topology`, choosing which underlying crypto
  module a build links against. Both Track O and Track C consume this
  same seam — neither independently links its own crypto module. One
  selection per project, never per jurisdiction (§0a).
- **Guarantees:** exactly one crypto module is linked per project; Track O
  and Track C provably use the same one; the choice made is recorded as
  build metadata for Track M's SBOM.
- **Out of scope:** doesn't ship or validate the crypto modules themselves
  — just the seam.
- **Tests:**
  - Unit: build-flag selection actually changes which module gets linked.
  - Integration: build against each supported crypto module, confirm
    Track O and Track C work identically against each.
  - Acceptance gate: a direct assertion that Track O and Track C agree on
    which crypto module is linked within the same build (no cross-variant
    diff job needed — Track N's was dropped per §0a, one code path).

### F6 — Doxygen infrastructure (added 2026-08-23)

Folded in from `plans/doxygen-generation.md`, which used to be its own
scoped-but-not-started track. Re-scoped: the one-time plumbing below is
Foundation's job; the ongoing "every template emits accurate doc-comments
for what it renders" discipline is Ground Rule 6 above, applying to every
track from here on — not something Foundation builds once and forgets.
`plans/doxygen-generation.md` itself stays alive as a living pitfall-table
reference (its §4), not a finished/removed plan — see that file's own
2026-08-23 status update.

- **Deliverables:** `Doxyfile` + CMake `doxygen` target
  (`add_custom_target`); `@mainpage`/`USE_MDFILE_AS_MAINPAGE` pointed at a
  landing page assembled from the relevant `USAGE.md` slices (§4 "What
  gets generated", §6 "Wiring the generated code into your own project",
  §11 "Notes & limits") — referenced, not re-authored, so there's one
  place to keep the narrative accurate.
- **Guarantees:** `doxygen` target builds HTML docs from the generated
  tree without needing any per-project configuration from the consumer.
- **Out of scope:** the per-template doc-comment content itself (Ground
  Rule 6's job, not this deliverable's); usage-example-as-integration-test
  generation (`plans/doxygen-generation.md` §5, a separate, larger,
  explicitly-deferred project).
- **Tests:**
  - A `doxygen`-gated test (skipped when the `doxygen` binary is absent,
    same pattern as the C++-toolchain-gated tests in `tests/CLAUDE.md`)
    that runs `doxygen` over a generated project and asserts zero
    warnings with `WARN_IF_UNDOCUMENTED = YES` — this is what makes
    Ground Rule 6 mechanically enforceable rather than just a written
    convention: a track that forgets a doc-comment fails this test, not
    just a review.
  - Acceptance gate: this test stays green as every later track lands —
    a regression here means some track's session skipped Ground Rule 6.

---

## Handoff — what you're giving the other four threads (five, since Thread 5 was added 2026-08-21)

Once this merges, every other thread can assume, without re-deriving it:

- `ComplianceContext` is threaded through every stage — read the active
  profile, don't reinvent config parsing.
- `field.is_phi` exists on every parsed field — check it, don't re-parse
  the grammar.
- `AuditSink` (no-op) exists and can be injected — call it, don't build
  your own audit mechanism.
- `CryptoBackend` selection seam exists — link against it if your track
  touches TLS or key material, don't pick your own crypto library.
- A tagged green baseline (F4) exists — diff your acceptance tests against
  it, not against an arbitrary earlier commit.
- The `doxygen` target/test (F6) exists — your track doesn't build this
  machinery, it just has to keep feeding it accurate doc-comments per
  Ground Rule 6, or the gated test catches the gap.

Point the five thread folders (`thread-1-data-and-keys/` through
`thread-5-device-interop/`) at this commit/tag once merged.

---

## Status vs. current harpia `dev` (added 2026-08-18)

Two tracks had already-shipped work folded in as dated update notes
directly in their session files rather than duplicated here — check
Track H (`thread-1-data-and-keys/track-h-schema-evolution.md`) and Track B
(`thread-2-transport-and-access/track-b-zmq-lifecycle.md`) before starting
either. One smaller
gap with no track yet — PostgreSQL on Windows — is in
`gaps-not-yet-tracked.md`. Doxygen generation is folded into this file
(F6 + Ground Rule 6, 2026-08-23) rather than its own scoping doc —
`plans/doxygen-generation.md` lives on as a pitfall-table reference, see
the F6 contract below. Track J (multi-language, Java) **moved out of
this plan entirely, 2026-08-23** — not medical-devices-specific work, now
`plans/multi-language-targets/` (`plans/java-target.md` and
`plans/multi-language-targets.md`, the two files this used to cite, are
deleted — merged into that standalone plan). See
`thread-4-platform-infra/track-j-java-target.md`'s pointer.

**Track I is fully superseded, not just partially shipped — found
2026-08-23:** the "largely aspirational" sha256-registry/continuable-
process system it was scoped to build already shipped 2026-08-19, via a
different, simpler mechanism (content-compared atomic writes, no
registry — see `util/CLAUDE.md`, `harpia.architecture.md`'s inline note).
Track I should be treated as done, not as a task — it isn't represented
at all in `thread-4-platform-infra/`, see that folder's README for why.
Full trace in `gaps-not-yet-tracked.md`'s "True crash/interrupt recovery"
entry. This also breaks Track L's stated dependency on Track I ("shares
registry version-stamp fields") — flagged as an open question in
`thread-4-platform-infra/track-l-versioning.md`, not resolved.

---

## Parallelism map (added 2026-08-18)

Written down because none of the individual session files state the
*cross-session* concurrency picture — each only describes its own internal
ordering. This is the answer to "how much of this can actually run at
once":

```
Foundation (F1-F5)              <- serial, single session, one blocking bottleneck
     |
     +---------------------------+---------------------------+---------------------------+
     |                           |                           |                           |
Session 1                  Session 2                   Session 3                   Session 4
 Track O  \                Track C                      Track E                     Track L (*)
           > parallel        then                          then                        |
 Track H  /                Track B                       Track F                  Track J / M / N
     |                                                                              (parallel,
     v                                                                              no deps on
 Track A                                                                            each other
  then                                                                              or on L)
 Track K
```
(*) Track I (originally shown here) is dropped entirely — see the
2026-08-23 update note above this section. Track L no longer depends on
it either, but has its own open question blocking it (see
`harpia_medical_master_plan.md`'s Track L contract) — it isn't a clean
parallel start the way this diagram's shape still implies.

**Reading it:**
- **One hard bottleneck:** Foundation. F1 alone touches `main.py` and every
  `Stage*` entry signature — "highest blast radius in the whole plan."
  Nothing downstream starts safely before this merges.
- **Four independent lanes after that, with no final convergence point.**
  Sessions 1-4 don't share files and none functionally depends on another
  *finishing* (only on Foundation) — genuinely parallelizable across
  separate repos/people/sessions, start to finish. This is simpler than it
  used to be: Track N's feature-parity diff (the old "wait for both
  Session 1 and Session 2 to land jurisdiction variants" convergence
  point) was dropped entirely per `harpia_medical_master_plan.md` §0a —
  `risk_class` is one project-wide floor, not a per-jurisdiction fan-out,
  so there are no variants left to diff.
- **Two lanes have their own internal split:**
  - Session 1 explicitly needs two people/repos at kickoff — Track O and
    Track H share no files and have no dependency on each other; they only
    converge when Track A starts (needs both merged first).
  - Session 4's middle stretch — Track J, Track M, and Track N — have no
    dependency on each other or on Track L, and (per the update above)
    no dependency on Sessions 1/2 either — run in any order. (Track I,
    once shown alongside these, is dropped entirely — 2026-08-23.)
- **Parallelism reduces calendar time, not engineering effort.** Track O
  and Track C in particular are each a substantial undertaking on their
  own (key management/envelope encryption/HSM integration; mTLS + full
  RBAC + sessions) — running them alongside other tracks doesn't make
  either one smaller or lower-risk, it just means they don't have to wait
  in line behind each other.
