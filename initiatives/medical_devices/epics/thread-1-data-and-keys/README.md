# Thread 1 — Data & Keys

**Restructured (2026-08-23)** from the single file `session-1-data-and-keys.md`
into this folder — one file per track — so each track's receive/give/touch
contract is easy to find without reading the other three tracks' detail.
Track letters (O/H/A/K) match `harpia_medical_master_plan.md`'s naming.
Each track file is further broken into small `Session <Track>.<n>` units
(one deliverable + its own tests, sized to fit a single sitting) — see the
2026-08-23 pilot note originally on this file's history for why: bundling
a whole track's contract into one open-ended session was blowing a day's
Claude Code quota per pickup (the message-versioning effort — shipped,
since deleted from `initiatives/`, see `Capability/CLAUDE.md` for what it left
behind — showed the same failure mode on an already-"scoped" plan, two
slices done together in one sitting).

Sessions 2, 3, 4, and 5 all got the same treatment on 2026-08-23 — see
`../thread-2-transport-and-access/`, `../thread-3-message-behavior/`,
`../thread-4-platform-infra/`, and `../thread-5-device-interop/`. All
five original sessions are now split.

- [track-o-key-management.md](histories/track-o-key-management.md) — pluggable
  `KeyProvider`, envelope encryption, rotation, crypto-shredding.
- [track-h-schema-evolution.md](histories/schema-evolution/track-h-schema-evolution.md) — child-table
  (map/repeated/repeated-composed) DB schema migration support.
- [track-a-db-encryption.md](histories/db-encryption/track-a-db-encryption.md) — DB field-level
  encryption for `phi` columns + audit-on-access wiring.
- [track-k-db-segregation.md](histories/db-segregation/track-k-db-segregation.md) — public/private
  DB segregation at environment level.

---

## What this whole thread receives from Foundation

Every track below lists which of these specific items it needs — not all
four tracks need all five. Stated once here so each track file doesn't
repeat the definition, only the reference:

- **F1** — `ComplianceContext` threaded through `main.py` and every stage.
- **F2** — `field.is_phi` flag available on every parsed field.
- **F3** — `AuditSink` (no-op stub) exists and is injectable.
- **F5** — `CryptoBackend` selection seam exists (which underlying crypto
  module a build links against).
- **F4** — a tagged regression baseline exists — the diff target for
  every acceptance gate in this thread.

(F1–F5 defined in `../foundation.md`.)

---

## Execution order across tracks

```
Track O: O.1 -> O.2 -> O.3 -> O.4 -> O.5   \
                                              > both fully merged, then:
Track H: H.1 -> H.2 -> H.3                 /

                    v
       A.1 -> A.2 -> A.3 -> A.4
                    v
                   K.1
```

- **Track O and Track H** share no files and have no functional
  dependency on each other — run as two separate sessions/repos from the
  start (see each file's own "Receives" section — Track H doesn't even
  need Foundation).
- **Track A** cannot start until every session in *both* Track O and
  Track H is merged.
- **Track K** starts immediately after Track A finishes, same
  session-line — it shares the `Database/` generator files A just
  modified.
- **If one of Track O/H finishes before the other:** don't idle — pick up
  a no-dependency task from `../thread-4-platform-infra/` (Track J, M, or
  N) as filler until the other merges.

---

## Definition of done (every session, every track in this thread)

- Unit tests for the construct/behavior that specific session introduces
  — not the whole track's suite, just that session's slice.
- Where a session's own tests can't fully close because a downstream
  track hasn't been built yet, that's named explicitly in both the
  session that defers it and the session that closes it later — never
  silently dropped. (See Track O's O.5 / Track A's A.4.)
- Full F4 regression baseline still passes.
- No cross-variant parity gate to wait on — Track N's feature-parity diff
  was dropped entirely per `harpia_medical_master_plan.md` §0a (one
  project-wide `risk_class` floor, not per-jurisdiction builds).
- **Ground Rule 6 (`../foundation.md`, added 2026-08-23):** any session
  that touches a consumer-facing template/adapter emits/updates accurate
  Doxygen doc-comments for what it touched, in the same session — not
  deferred. Add a row to `initiatives/doxygen-generation/doxygen-generation.md` §4 if the work
  surfaces a pitfall not already listed there.

## Watch for (thread-wide)

- Don't start any Track A session until **every** session in **both**
  Track O and Track H shows a merged commit on `main`.
- Track K.1 starts immediately after Track A finishes, same
  session-line — don't hand it to a fresh session, it shares files with
  what A just touched.
- Track O's O.5 and Track A's A.4 are a matched pair — don't consider
  Track O "fully tested" at O.5 without coming back for A.4; don't skip
  A.4 thinking A.1–A.3's tests already cover it.
