# Session 0 — Foundation

Serial. Single session. Must merge to `main` before any other session
(1–4) starts on any repo copy. This is the one synchronization point
everyone else waits on.

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

---

## What this session delivers

| ID | Task | Touches | Notes |
|---|---|---|---|
| F1 | `ComplianceContext`: parse `project.harpia.yaml` (`jurisdiction[]`, `risk_class`, `topology`, `phi_handling`), thread it through `main.py` and every stage entry point | `main.py`, every `Stage*` entry signature | Highest blast radius in the whole plan. Fail-safe default (strictest settings) when unset/ambiguous. Plural `jurisdiction` means **fan-out**: one compile-time build variant per listed jurisdiction, not one instance satisfying all simultaneously. |
| F2 | `phi` (sensitive-field) modifier in the grammar + AST | `LexicalAnalizer/`, `Message/` | Needed before DB encryption, redacted `toString`, or audit-on-access can be built. Sensitivity is a **per-field** modifier, same category as `optional`/`required`/`unique` — never a whole-message property. |
| F3 | `AuditSink` interface — abstract/no-op stub only, no implementation yet | new `Compliance/` module | Real implementations happen in Track A (DB) and Track C (comm), independently. Decision closed: **compile-time strategy** — separate build variant per jurisdiction. Build the stub already shaped for that (strategy-pattern, not a runtime-selected composite). |
| F4 | Golden-snapshot / regression baseline confirmed green before anything branches | `tests/` | Every later track's "acceptance gate" diffs against this. |
| F5 | `CryptoBackend` selection point: compile-time seam choosing which underlying crypto module gets linked per jurisdiction build (e.g. standard vs. FIPS-validated OpenSSL) | new `Crypto/backend.py` (or build-flag/CMake option) | Both Track O (key-wrap/envelope-encryption) and Track C (TLS stack) must consume this, not each pick their own — prevents silent drift onto different crypto modules within the same jurisdiction build. |

**Exit criterion:** F1–F5 merged to `main`, all existing tests green.

---

## Contracts

### F1 — ComplianceContext plumbing
- **Deliverables:** `Compliance/context.py` defining
  `ComplianceContext{jurisdiction[], risk_class, topology, phi_handling}`;
  `project.harpia.yaml` parser; `main.py` and every `Stage*` entry point
  updated to receive it.
- **Guarantees after merge:** every stage has access to the active
  compliance profile; an invalid/unknown enum value is a hard error at
  generation start, never silently ignored; missing config defaults to the
  strictest profile with a logged warning; a plural `jurisdiction` list is
  fan-out, not a runtime-union requirement.
- **Out of scope:** no jurisdiction-specific *behavior* yet — plumbing only.
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
- **Out of scope:** real jurisdiction-specific audit logic — built
  compile-time-per-jurisdiction in Track O and Track C, not here.
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
- **Deliverables:** a single compile-time seam (build flag/CMake option)
  choosing which underlying crypto module a build links against. Both
  Track O and Track C consume this same seam — neither independently
  links its own crypto module.
- **Guarantees:** exactly one crypto module is linked per build variant;
  Track O and Track C provably use the same one; the choice made per
  jurisdiction is recorded as build metadata for Track M's SBOM.
- **Out of scope:** doesn't ship or validate the crypto modules themselves
  — just the seam.
- **Tests:**
  - Unit: build-flag selection actually changes which module gets linked.
  - Integration: build a variant with each supported crypto module,
    confirm Track O and Track C work identically against each.
  - Acceptance gate: Track N's feature-parity CI diff asserts Track O and
    Track C agree on which crypto module is linked within the same build.

---

## Handoff — what you're giving the other four sessions

Once this merges, every other session can assume, without re-deriving it:

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

Point the four session files (`session-1-data-and-keys.md` through
`session-4-platform-infra.md`) at this commit/tag once merged.

---

## Status vs. current harpia `dev` (added 2026-08-18)

Two tracks had already-shipped work folded in as dated update notes
directly in their session files rather than duplicated here — check
Track H (`session-1-data-and-keys.md`) and Track B
(`session-2-transport-and-access.md`) before starting either. One smaller
gap with no track yet — PostgreSQL on Windows — is in
`gaps-not-yet-tracked.md`. Doxygen generation has its own scoping doc,
`plans/doxygen-generation.md`. Track J (Session 4, multi-language) has
a resolved dependency on `plans/multi-language-targets.md` — see the
update note on that track in `session-4-platform-infra.md`.

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
 Track O  \                Track C                      Track E                     Track I
           > parallel        then                          then                        then
 Track H  /                Track B                       Track F                     Track L
     |                                                                                    |
     v                                                                              Track J / M /
 Track A                                                                            N-static
  then                                                                              (parallel,
 Track K                                                                             no deps
                                                                                      on each
                                                                                      other or
                                                                                      on I/L)
     \___________________________________________+_________________________________/
                                                   |
                                          Track N's feature-parity
                                          diff -- LAST, gated on
                                          Session 1 (O/A) AND
                                          Session 2 (C) both landing
                                          compile-time jurisdiction
                                          variants first
```

**Reading it:**
- **One hard bottleneck:** Foundation. F1 alone touches `main.py` and every
  `Stage*` entry signature — "highest blast radius in the whole plan."
  Nothing downstream starts safely before this merges.
- **Four independent lanes after that:** Sessions 1-4 don't share files and
  none functionally depends on another *finishing* (only on Foundation).
  Genuinely parallelizable across separate repos/people/sessions.
- **Two lanes have their own internal split:**
  - Session 1 explicitly needs two people/repos at kickoff — Track O and
    Track H share no files and have no dependency on each other; they only
    converge when Track A starts (needs both merged first).
  - Session 4's middle stretch — Track J, Track M, and Track N's
    static/fuzz half have no dependency on each other or on Track I/L —
    a third internal split, if there's capacity for it.
- **One convergence point, at the very end, not the start:** Track N's
  feature-parity diff needs compile-time jurisdiction variants from
  *both* Session 1 (Track O/A) and Session 2 (Track C) to exist before it
  has anything to diff. Don't activate it early (Session 4's own file
  already says this) — it's the one place the fan-out has to rejoin.
- **Parallelism reduces calendar time, not engineering effort.** Track O
  and Track C in particular are each a substantial undertaking on their
  own (key management/envelope encryption/HSM integration; mTLS + full
  RBAC + sessions) — running them alongside other tracks doesn't make
  either one smaller or lower-risk, it just means they don't have to wait
  in line behind each other.
