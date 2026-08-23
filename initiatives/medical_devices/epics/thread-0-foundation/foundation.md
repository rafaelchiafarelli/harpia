# Session 0 — Foundation

## Required reading — design rules reference (added 2026-08-23)

[`harpia_sensitive_data_design_rules.md`](../../harpia_sensitive_data_design_rules.md)
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

## What this session delivers

| ID | Task | Touches | Notes |
|---|---|---|---|
| F1 | `ComplianceContext`: parse `project.harpia.yaml` (`risk_class`, `topology`, `phi_handling`, `jurisdiction[]` — paperwork routing only), thread it through `main.py` and every stage entry point | `main.py`, every `Stage*` entry signature | Highest blast radius in the whole plan. Fail-safe default (strictest settings) when unset/ambiguous. `risk_class` is the single project-wide hardening floor — no per-jurisdiction build variants, no fan-out (§0a). `jurisdiction[]` has zero effect on generated code; it only feeds Track M's doc-template selection. |
| F2 | `phi` (sensitive-field) modifier in the grammar + AST | `LexicalAnalizer/`, `Message/` | Needed before DB encryption, redacted `toString`, or audit-on-access can be built. Sensitivity is a **per-field** modifier, same category as `optional`/`required`/`unique` — never a whole-message property. |
| F3 | `AuditSink` interface — abstract/no-op stub only, no implementation yet | new `Compliance/` module | Real implementations happen in Track A (DB) and Track C (comm), independently. One implementation per project, gated by `risk_class`, not per jurisdiction (§0a). Build the stub already shaped for that. |
| F4 | Golden-snapshot / regression baseline confirmed green before anything branches | `tests/` | Every later track's "acceptance gate" diffs against this. |
| F5 | `CryptoBackend` selection point: compile-time seam choosing which underlying crypto module gets linked (e.g. standard vs. FIPS-validated OpenSSL) | new `Crypto/backend.py` (or build-flag/CMake option) | Both Track O (key-wrap/envelope-encryption) and Track C (TLS stack) must consume this, not each pick their own — prevents silent drift onto different crypto modules. One selection per project, driven by `risk_class`/`topology`, not per jurisdiction (§0a). |
| F6 | Doxygen infrastructure (added 2026-08-23): `Doxyfile` + CMake `doxygen` target; `@mainpage`/`USE_MDFILE_AS_MAINPAGE` pointed at a landing page assembled from `USAGE.md` (§4/§6/§11) | new `Doxyfile`, CMake target | One-time plumbing only — see `initiatives/doxygen-generation/doxygen-generation.md` §2. The *ongoing* per-template doc-comment discipline is Ground Rule 6 above, not a Foundation task: every later track owns keeping its own templates' comments accurate, this just builds the machinery that displays them. |

**Exit criterion:** F1–F6 merged to `main`, all existing tests green.

---

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
