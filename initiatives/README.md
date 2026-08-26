# Initiatives index

Scoping/planning docs for work that's bigger than a single session. Each doc
below is either a **live plan** (being executed, slice by slice) or a
**scoping doc** (recommendation + sizing, not yet started). `README.md`'s
top-level "Known gaps" section stays the live, authoritative list of
implemented-vs-missing features; this index is for the *why/how* behind the
bigger unimplemented pieces, and for backlog items that don't have their own
doc yet.

## STRUCTURAL TODO (flagged 2026-08-23, fix next session — nothing below has been touched yet)

1. **`medical_devices/epics/thread-N-*/` folders each bundle multiple
   "Track" files, now nested one level deeper under `histories/<name>/`**
   (e.g. `thread-1-data-and-keys/` contains
   `histories/track-o-key-management.md`,
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
   shipped in full (J.1–J.27) and was removed from `initiatives/`
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
   already live as its own top-level folder, `initiatives/doxygen-generation/`
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
| [medical_devices/](medical_devices/harpia_medical_master_plan.md) | Scoped, not started — compliance profile for regulated deployments |
| [medical_devices_implementation/](medical_devices_implementation/README.md) | **Live plan**, started 2026-08-25 (branch `feature/test-projects-blueprint`) — drive each of the 20 `TestProjects/` example projects to buildable/runnable code. Room epics 0–4 + cross-cutting epics 5–8. ICU C++ devices + the 5 infra scaffolds generate/build/run; everything else not started. Uses a `epics/<N-room>/histories/<device>/` layout — a third folder convention, see STRUCTURAL TODO above. |
| [feature-examples/](feature-examples/README.md) | **Partly shipped.** EX.1 (the `HarpiaTest` shared-fixture cleanup — `pope`/`king`/`queenBee` folded into `queen`) shipped 2026-08-24 (`f247b6c`). EX.2–EX.8 — one small runnable example per generated feature (gRPC, SOAP, XML, ZMQ, capability negotiation, credential-gated access) + an index — not started. |
| [doxygen-generation.md](doxygen-generation/doxygen-generation.md) | **Folded into Foundation's F6 + Ground Rule 6, 2026-08-23** — shipped and merged to `dev` (the Foundation thread itself was then removed, see `medical_devices/epics/handoff-document.md`); no longer a deferred track. This file now lives on as a living pitfall-table reference every track appends to as it builds. Not medical-devices-specific despite living in that plan's Foundation — the rule applies repo-wide. |

Finished plans are removed from this index once done — the shipped
behavior is documented in the code's own `CLAUDE.md`/architecture docs,
not preserved here. (Postgres backend and crash/interrupt recovery were
both here; both shipped and are now covered by `Database/CLAUDE.md` /
`util/CLAUDE.md` respectively — crash/interrupt recovery's
content-compared atomic-write mechanism, see `util/CLAUDE.md`.
`message-versioning.md` — stable wire field numbers, JSON/XML
parse-boundary hardening, and a capability handshake across all four
transports — shipped 2026-08-22/23 and was removed 2026-08-23; its
design rationale is now distributed across `message/CLAUDE.md`,
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
`examples/android_consumer/README.md` (the Android verification account,
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
