# Harpia — completeness assessment (2026-09-19)

**What it is:** a Python code generator that turns a custom `.harpia` DSL
definition into compilable C++ (and Java) transport/serialization/database code
— REST, SOAP, gRPC, ZMQ, DB CRUDL — with an optional medical-device compliance
profile bolted on via config.

**Test suite, verified live this pass:** `Docker/run.sh pytest UnitTests/ -q`
→ **550 passed, 4 skipped, 0 failed** (28 min). The 4 skips are the opt-in
live-PostgreSQL tests (`Docker/run_pg_tests.sh` covers those separately, last
verified 2026-09-02). No unconditional skips anywhere in `UnitTests/` — every
`pytest.mark.skip` in the tree is a `skipif` gated on a real environment
condition (JDK, live PG), not a silently-disabled test. This bar is real, not
aspirational.

## Just closed: message-level-hardening

Confirmed complete, not just claimed complete. All 5 tasks of
`protected-open-modifiers` merged `tasks → … → dev`; the tests it claims to
have (`test_protected_open_modifiers.py`, `test_mtls_optional_mode_spike.py`,
`test_mixed_mode_fixture.py`, `test_message_hardening_gate.py`) actually
exist and are in the 550 that just passed. This is what closes the
"multi-tier RBAC" gap the last assessment (2026-09-13) flagged as the best
medium-effort bet — it's done, not just scoped, as of this session.

## Two real problems, not five imaginary ones

Most of what could be "bullshit" in a project this size — stale claims,
scope-creep, undisclosed gaps — turned out fine on inspection. Two things
didn't:

### 1. "Encrypts it" is doing a lot of work in USAGE.md §9

`USAGE.md` §9 tells a user: tag a field `phi` and "the DAO encrypts it on
create/update and decrypts on read/list." That's true in the sense that a
transform happens. It is not true in the sense a reader would assume — the
actual cipher, everywhere, right now, is a placeholder **XOR**
(`Crypto/backend.py`'s own docstring: *"no real cryptographic operations are
implemented anywhere in this repo yet"*; `Crypto/CLAUDE.md`: *"All still
placeholder XOR: the real cipher lands when a backend is bound to the F5
seam"*; `Crypto/runtime/harpia_encrypted_column.h:20`: *"The XOR 'cipher' is
inherited from the O.* placeholder KeyProvider"*). The envelope-encryption
machinery around it (KEK/DEK separation, rotation, per-DEK crypto-shred,
zeroization, audit-on-access) is real and well-built — but it's wrapped
around a cipher that provides no confidentiality at all.

This is disclosed honestly in `Crypto/CLAUDE.md`, a doc written for whoever
is *building* Harpia. It is not disclosed anywhere in `USAGE.md` or
`README.md`, the docs read by whoever is *using* Harpia to handle PHI. For a
project whose stated audience includes medical-device data, that's the gap
that actually matters — not "a feature is missing" but "a feature reads as
shipped to the one audience who'd stop and ask about it if they knew."
Fix is cheap (a one-line caveat in §9 and the README's compliance bullet);
not fixed here because it's a docs-honesty call for Rafael, not a
docs-completeness one — flagging rather than unilaterally deciding the
wording.

### 2. README contradicts itself about Windows ZMQ CURVE, right now, today

Two Known-Gaps bullets in the same file disagree:

- `README.md:58-59` (Transport encryption bullet, last touched
  2026-08-26): *"the Windows vcpkg `zeromq` `curve`+`sodium` build is
  unverified (Linux/Docker only so far)."*
- `README.md:82-89` (Windows-as-a-target bullet, rewritten in
  `d46d081`, 2026-09-13): *"the ZMQ server/client demo (incl.
  `-DUSE_ZMQ_CURVE=ON`) … the PostgreSQL backend … against a live
  server"* — ✅, verified.
- `USAGE.md` §16 agrees with the second one, and the underlying commit
  history confirms it: `a868eda` "Build- and live-session-verify
  PostgreSQL on Windows via vcpkg" (2026-08-22) is a real commit, not a doc
  edit.

The **2026-09-13 fix commit** (`d46d081`, "fix(docs): correct stale README
claims on YAML and Windows verification") updated the second bullet but
missed the first — so the correction and the stale claim it was meant to
replace are still both sitting in the same file. Worth noting: the
2026-09-13 assessment claimed this was "Fixed 2026-09-13" — it wasn't, fully.
That's the actual lesson here, more than the one-line fix itself: a doc-fix
commit needs to grep for every place a claim is duplicated, not just the one
place it was noticed. One-line fix: delete the stale clause at
`README.md:58-59` (the ✅ bullet below it already says everything true about
Windows CURVE).

## Remaining gaps, sorted by effort to close

All confirmed by reading current code/tasks this pass, not carried over from
memory.

| Effort | Gap | Evidence |
|---|---|---|
| Trivial | **The two doc issues above.** | See above — a few lines each. |
| Small | **No CI.** Zero `.github/workflows` still. | `Initiatives/ci-pipeline/` has 2 tasks written (`1-workflow-skeleton`, `2-image-layer-caching`), 0 done. Same as last pass — nothing moved here. |
| Small | **Multi-peer ZMQ transport claims still unverified.** | `Initiatives/transport-multipeer-coverage/` — 6 tasks scoped, 0 done. Unchanged since last pass. |
| Medium | **Doxygen doc-comments — still 0% coverage.** | `grep -rl '/\*\*' --include='*.tmpl'` across all 39 non-third_party templates: 0 hits, confirmed fresh this pass. Plumbing (F6) works; nobody has written a comment yet. |
| Large | **`go-target` — only the seam has tasks.** | `main.py:174` still has the literal `if genLang == "java":` the seam is meant to replace; zero `.go` files anywhere; `lang-backend-seam` epic (3 tasks) is the only one with tasks written of 13 epics. |
| Large | **`python-target` — nothing.** | 0 tasks anywhere in the tree; explicitly gated on `go-target`'s seam per its own README. Unstarted, as designed. |

## What's not a problem (checked, not assumed)

- **Branch hygiene:** 47 branches, 45 merged into `dev`. This looks like a
  lot but it's the workflow working as designed — every task/epic/initiative
  level keeps its own branch permanently. Only `initiatives/test-progress-scoping`
  (not started) and `main` (expected to lag `dev`) are unmerged.
- **No stray TODO/FIXME/XXX markers** anywhere in real source (checked
  outside `third_party/` and tests).
- **No dead code found this pass** — the GuiAdapter removal from last time
  stuck, nothing new turned up.
- **The `harpia_two/three/four` stale duplicate directories** noted last
  assessment are gone from the workspace.

## Recommendation

Fix the two doc issues first — they're minutes of work and one of them
(the PHI/XOR disclosure) is a trust issue, not a completeness one. After
that, CI and the multi-peer tests remain the best small bets for the same
reason as last time. Nothing regressed; the one thing that was supposed to
move (message-level-hardening) moved, cleanly, with tests to show for it.
