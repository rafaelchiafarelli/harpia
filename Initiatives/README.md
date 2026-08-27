# Initiatives index

Scoping/planning docs for work that's bigger than a single session. Each doc
below is either a **live plan** (being executed, slice by slice) or a
**scoping doc** (recommendation + sizing, not yet started). `README.md`'s
top-level "Known gaps" section stays the live, authoritative list of
implemented-vs-missing features; this index is for the *why/how* behind the
bigger unimplemented pieces, and for backlog items that don't have their own
doc yet.

## How to work an `epics/` thread — READ THIS FIRST

Learned the hard way on the sensitive-data effort (2026-08-27). Follow it or
expect rework:

1. **Plan docs are frozen references, not status logs.** `medical_devices/
   sensitive-data-implementation-roadmap.md`, `harpia_medical_master_plan.md`,
   `harpia_sensitive_data_design_rules.md` — **do not edit them** to record
   progress. The plan is the plan. Status lives only in `epics/`.
2. **`track-*.md` holds the contract only** — Receives / Gives / Files this
   track touches / Watch for, plus a pointer list to the session files.
   Never cram session detail or a running narrative into it.
3. **One session = one small file under that track's `tasks/`** (see the
   sibling threads: ~300–700 bytes, Depends on / Deliverable / Out of scope
   / Tests). If a track file still has its sessions written inline,
   restructure it to match its siblings the first time you touch it
   (`git mv` into a `histories/<name>/` subfolder + `tasks/`; keep each
   session's original wording; fix every `[](…)` link).
4. **The done marker is the FILENAME, not the content.** When a session
   lands, `git mv` its task file to add a `-done` suffix
   (`crypto-shredding.md` → `crypto-shredding-done.md`) — same convention
   Foundation used. A whole finished thread folder gets `-done` too. No
   `**Status:**` line, no "Landed in `<hash>`" line inside — `ls` the dir
   and `git log -- <impl file>` are the record. (Don't put a commit hash
   in a file that's part of that same commit and then `--amend` — the hash
   changes and you chase your tail.)
5. **Use the `epics/` naming in every hand-off and message** — thread
   folder / track file / session id (`O.4`, `D.3`). Never invented labels
   like "Phase 3c".
6. **A task that belongs to another track goes in that track's `tasks/`**,
   not shoe-horned into the one you're working on (e.g. a
   `ComplianceReport/` note is Track M's, even when Track D triggered it).
7. **Run the full suite in Docker before every commit** (invocation is in
   whatever `NEXT_SESSION.md` exists). Each session's code lands additive
   where possible — no generator change, no golden movement — until a
   session explicitly says otherwise.

### Branch & merge flow (adopted 2026-08-27, sensitive-data `phi` side)

8. **Task files are numbered per track, in execution order.** Each
   `tasks/` file carries a numeric prefix that restarts at `1` per track
   (`1-scalar-child-table-migration.md`, `2-map-…`, `3-composed-…`). The
   number is the implementation order *and* the branch name. The `-done`
   suffix (rule 4) goes *after* the name: `1-…-migration-done.md`.
9. **One session = one branch**, named
   `features/medical_devices/thread-<N>/<track-folder>/<n>-<task-name>`
   (e.g. `features/medical_devices/thread-1/schema-evolution/1-scalar-child-table-migration`).
   Branch it off `dev`. When a track's sessions genuinely build on each
   other (H.2 reuses H.1's wiring), branch the next session off the
   *previous session's branch* instead of `dev`, so the code is present —
   but still merge one session at a time (next point).
10. **Per session, in order:** implement → regenerate goldens
    (`HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest UnitTests/test_golden.py
    UnitTests/test_golden_java.py`) and **review the diff** → full suite
    green in Docker → **commit the implementation** → **`git mv` the task
    file to its `-done` name in a second commit on the same branch** →
    `git checkout dev && git merge --no-ff <branch>` (one merge bubble per
    session, message `Merge Track <X> / Session <X.n> (<title>) into dev`)
    → `git push origin dev` → branch the next session off `dev`. Never
    edit the frozen plan docs (rule 1); never merge/push `main`.
11. **A new `phi`/`critical` fixture goes in `HarpiaTest/Include/*.harpia`,
    not `test.harpia`** — only the root file's text feeds the pinned
    `HASH`, so an Include-file edit moves golden *content* for the touched
    messages but leaves every `HASH = "…"` constant alone. `.harpia`
    comments are lexed like code: letters/digits/spaces and
    `. , ( ) { } [ ] ; = < > + - * /` only — a `:` / `'` / `"` / `_` /
    backtick anywhere in a `//` comment hard-errors the whole file.

## STRUCTURAL TODO (flagged 2026-08-23, fix next session — nothing below has been touched yet)

1. **`medical_devices/epics/thread-N-*/` folders each bundle multiple
   "Track" files, now nested one level deeper under `histories/<name>/`**
   (e.g. `thread-1-data-and-keys/` contains
   `histories/key-management/track-o-key-management.md`,
   `histories/schema-evolution/track-h-schema-evolution.md`,
   `histories/db-encryption/track-a-db-encryption.md`,
   `histories/db-segregation/track-k-db-segregation.md`). Under the
   correct model, each of those tracks (O, H, A, K, B, C, E, F, P, Q, R,
   J, L, M, N) should be its own **Thread** directly under the
   `medical_devices` plan — a feature in its own right — not grouped
   inside a wrapper "Thread N" folder alongside sibling tracks. The
   session breakdowns inside each track file (O.1–O.5, etc.) are the
   right grain and don't need rework, just re-parenting: they become that
   Thread's own sessions directly, no intermediate Track layer.
2. ~~`multi-language-targets/thread-1-java-target/histories/track-j-java-target.md`
   has the same extra layer~~ **moot as of 2026-08-25** — the Java thread
   shipped in full (J.1–J.27) and was removed from `Initiatives/`
   entirely per this repo's finished-plans convention, so there's no
   longer a structure to collapse here.
3. **`doxygen-generation.md` was folded into Foundation's F6 + Ground Rule 6**
   (the Foundation thread itself has since shipped, merged to `dev`, and
   been removed — see `medical_devices/epics/handoff-document.md`) instead
   of staying its own top-level epic. Per
   the corrected model it belongs alongside `medical_devices/` and
   `multi-language-targets/` as its own plan folder, with its own
   thread/session breakdown — not absorbed into a different epic's
   Foundation. Undo that fold and re-scope it as its own plan. (It does
   already live as its own top-level folder, `Initiatives/doxygen-generation/`
   — the fold this TODO flags is the *content* still being duplicated
   into Foundation's F6/Ground Rule 6, not a location problem.)

Also needs a decision next session, not assumed here: the current
"Thread 1 needs two concurrent session-lines for Track O and Track H"
framing (parallel execution of sibling tracks) doesn't have an obvious
home once each track becomes its own Thread — that parallelism note
probably belongs at the **Plan** level (an execution/parallelism map
across Threads), not nested inside one Thread's own file. Work this out
when doing the actual restructure, don't guess it into this TODO.

**Nothing in the repo has been changed to fix this yet** — this section
is only the flag, per explicit instruction. The existing
`medical_devices/epics/thread-*/` folders (and the doxygen-generation
fold into Foundation) are still in their 2026-08-23 shape below and need
the re-parenting described above. (Item 2's `multi-language-targets/`
case is now moot — see above.)

| Doc | Status |
|---|---|
| [medical_devices/](medical_devices/harpia_medical_master_plan.md) | **In progress.** Foundation F1–F6 shipped (plumbing stubs, merged to `dev`, thread removed — see `epics/handoff-document.md`). Sensitive-data behavior (`phi` + `critical`) being built on branch `feature/sensitive-data-implementation`, merged to `dev` in slices. **Done: `epics/thread-6-critical-and-phi-done/`** — Track D, the `critical` delivery-guarantee axis the master plan assumed already existed (modifier + `harpia_delivery.h` runtime + `ZmqAdapter` wiring + a real-socket send/receive integration test). **Done: Track O** (key management) — `epics/thread-1-data-and-keys/histories/key-management/` (O.1–O.5, all `-done`). **Done: Track H** (schema-evolution, `histories/schema-evolution/`, H.1–H.3 `-done`) — repeated-scalar / map / repeated-composed child-table migration in `migrate_<table>()`. **Done: Track A** (DB field-level encryption, `histories/db-encryption/`, A.1–A.4 `-done`) — `phi` columns envelope-encrypted on the DAO write path / decrypted on read via Track O's `KeyProvider` (`Crypto/runtime/harpia_encrypted_column.h`, `CrudlAdapter`), one `AuditSink.record()` per `phi` CRUDL op, `project.harpia.yaml` landed at the repo root, KEK-rotation + backend-swap proofs closed (from O.5). **Done: Track K** (public/private DB segregation, `histories/db-segregation/`, K.1 `-done`) — `Database/DbRegistryAdapter.py` emits one project-wide `generated/cpp/db/harpia_db_registry.h`: a `constexpr` registry of every table tagged PUBLIC/PRIVATE with an owner project name (`project.harpia.yaml` → `project:`, new `ComplianceContext.project`), plus `db_access_check()` refusing a PRIVATE table cross-project while keeping PUBLIC ones reachable; purely additive (goldens only gain the one file). All merged to `dev` (through `44ceec7`, 2026-08-27; Track K on top). **In progress: Track F** (`phi` redaction / serialization, `thread-3-message-behavior/histories/serialization/`) — F.1 `-done` (new `YamlAdapter/`: reflection-based `harpia_yaml.h` + wrappers), F.2 `-done` (new `SerializeAdapter/`: one `harpia::serialize::to_string(msg, Format)` dispatch façade over the three unchanged engines — JSON/XML output byte-identical, acceptance gate held); F.3 (uniform `phi` redaction, hooked in the F.2 façade) next, then F.4 (audited `--allow-phi-print`) and F.5 (round-trip + `ComplianceReport/` note). The [roadmap](medical_devices/sensitive-data-implementation-roadmap.md) is the frozen plan; `epics/` carries live status. |
| [feature-examples/](feature-examples/README.md) | **Partly shipped.** EX.1 (the `HarpiaTest` shared-fixture cleanup — `pope`/`king`/`queenBee` folded into `queen`) shipped 2026-08-24 (`f247b6c`). EX.2–EX.8 — one small runnable example per generated feature (gRPC, SOAP, XML, ZMQ, capability negotiation, credential-gated access) + an index — not started. |
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | **Folded into Foundation's F6 + Ground Rule 6, 2026-08-23** — shipped and merged to `dev` (the Foundation thread itself was then removed, see `medical_devices/epics/handoff-document.md`); no longer a deferred track. This file now lives on as a living pitfall-table reference every track appends to as it builds. Not medical-devices-specific despite living in that plan's Foundation — the rule applies repo-wide. |

Finished plans are removed from this index once done — the shipped
behavior is documented in the code's own `CLAUDE.md`/architecture docs,
not preserved here. (Postgres backend and crash/interrupt recovery were
both here; both shipped and are now covered by `Database/CLAUDE.md` /
`Util/CLAUDE.md` respectively — crash/interrupt recovery's
content-compared atomic-write mechanism, see `Util/CLAUDE.md`.
`message-versioning.md` — stable wire field numbers, JSON/XML
parse-boundary hardening, and a capability handshake across all four
transports — shipped 2026-08-22/23 and was removed 2026-08-23; its
design rationale is now distributed across `Message/CLAUDE.md`,
`Capability/CLAUDE.md`, and the three `*CapabilityAdapter/CLAUDE.md`
files it fed. The one unrelated finding it surfaced — a `third_party/asio`
vendoring gap — wasn't part of the plan and was resolved 2026-08-23 by
re-vendoring the missing headers (see `HttpCapabilityAdapter/CLAUDE.md`).
`multi-language-targets/`
(Java as a full generation target, symmetric with C++, plus the
motivating on-device Android consumption verification) shipped in full —
J.1–J.27 — 2026-08-25 and was removed the same day; its design rationale
is now distributed across `GradleAdapter/CLAUDE.md` (build-time codegen
decision), `JavaJsonAdapter/CLAUDE.md`/`JavaXmlAdapter/CLAUDE.md` (full
protobuf runtime vs. `javalite` decision), `JavaZmqAdapter/CLAUDE.md`
(JeroMQ/CURVE), `Database/CLAUDE.md` (why a cross-language `DbBackend`
seam is still deliberately undesigned), and
`HarpiaTest/app_example/android_consumer/README.md` (the Android verification account,
including the one real ART-incompatibility bug it found).)

## Backlog

Open items not yet big enough for their own scoping doc. Add to this list
piecemeal as items get scoped or come up — no need to do it all at once.

- **Python as language #3** (after Java, which shipped 2026-08-25 — see
  the "Finished plans" note above). Selection history: Python was the
  original per-stage-cost recommendation (2026-08-11), but a concrete
  business need — an existing Android fleet wanting harpia-generated Java
  code — overrode that in a 2026-08-22 addendum; Python was never
  dropped, just deferred. Also note (`Database/CLAUDE.md`): a
  cross-language `DbBackend`-style seam was deliberately left undesigned
  after Java, the same way `Database/backends/`'s own dialect seam waited
  for Postgres as a second case — Python would be the third language data
  point, likely the trigger to finally design one. Multi-session sized,
  don't start as a "quick session."
- **Smaller/unscoped:** no YAML serialization, no multi-tier RBAC (single
  flat credential everywhere).
