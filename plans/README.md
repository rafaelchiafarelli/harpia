# Plans index

Scoping/planning docs for work that's bigger than a single session. Each doc
below is either a **live plan** (being executed, slice by slice) or a
**scoping doc** (recommendation + sizing, not yet started). `README.md`'s
top-level "Known gaps" section stays the live, authoritative list of
implemented-vs-missing features; this index is for the *why/how* behind the
bigger unimplemented pieces, and for backlog items that don't have their own
doc yet.

## STRUCTURAL TODO (flagged 2026-08-23, fix next session — nothing below has been touched yet)

The 2026-08-23 restructuring session got the hierarchy wrong and needs to
be redone. The correct model, as stated by the user:

- **Plans are epics.** `medical_devices/`, `multi-language-targets/`, and
  `doxygen-generation` are each their own epic/plan.
- **Threads are features** — how many threads a plan needs to cover one
  part of the epic. One thread = one feature.
- **Sessions are tasks** — how many sessions a thread needs to complete
  that feature. One session = one deliverable, sized to fit a single
  sitting (this part was built correctly).

Three levels only: **Plan → Thread → Session.** What actually got built
2026-08-23 has an extra, unwanted level in two places, and moved a whole
plan into the wrong place in a third:

1. **`medical_devices/schedule/thread-N-*/` folders each bundle multiple
   "Track" files** (e.g. `thread-1-data-and-keys/` contains
   `track-o-key-management.md`, `track-h-schema-evolution.md`,
   `track-a-db-encryption.md`, `track-k-db-segregation.md`). Under the
   correct model, each of those tracks (O, H, A, K, B, C, E, F, P, Q, R,
   J, L, M, N) should be its own **Thread** directly under the
   `medical_devices` plan — a feature in its own right — not grouped
   inside a wrapper "Thread N" folder alongside sibling tracks. The
   session breakdowns inside each track file (O.1–O.5, etc.) are the
   right grain and don't need rework, just re-parenting: they become that
   Thread's own sessions directly, no intermediate Track layer.
2. **`multi-language-targets/thread-1-java-target/track-j-java-target.md`**
   has the same extra layer — a "thread" folder wrapping a single "track"
   file that holds all 27 sessions. Should collapse: the Java work is one
   Thread (a feature of the `multi-language-targets` epic), and J.1–J.27
   are that Thread's sessions directly.
3. **`doxygen-generation.md` was folded into `medical_devices/schedule/foundation.md`**
   (as F6 + Ground Rule 6) instead of staying its own top-level epic. Per
   the corrected model it belongs alongside `medical_devices/` and
   `multi-language-targets/` as its own plan folder, with its own
   thread/session breakdown — not absorbed into a different epic's
   Foundation. Undo that fold and re-scope it as its own plan.

Also needs a decision next session, not assumed here: the current
"Thread 1 needs two concurrent session-lines for Track O and Track H"
framing (parallel execution of sibling tracks) doesn't have an obvious
home once each track becomes its own Thread — that parallelism note
probably belongs at the **Plan** level (an execution/parallelism map
across Threads), not nested inside one Thread's own file. Work this out
when doing the actual restructure, don't guess it into this TODO.

**Nothing in the repo has been changed to fix this yet** — this section
is only the flag, per explicit instruction. The existing
`medical_devices/schedule/thread-*/` and `multi-language-targets/`
folders (and the doxygen-generation fold into Foundation) are still in
their 2026-08-23 shape below and need the re-parenting described above.

| Doc | Status |
|---|---|
| [multi-language-targets/](multi-language-targets/README.md) | **Restructured 2026-08-23** — `multi-language-targets.md` and `java-target.md` merged and deleted, replaced by a thread/session folder (same pattern as `medical_devices/schedule/`). Scoped, not started. Java picked ahead of Python for a concrete reason (existing Android fleet); 27-session breakdown (one deliverable + tests each) in `thread-1-java-target/track-j-java-target.md`; Android is the consumer of a subset (see `thread-1-java-target/README.md` §7) |
| [medical_devices/](medical_devices/harpia_medical_master_plan.md) | Scoped, not started — compliance profile for regulated deployments |
| [doxygen-generation.md](doxygen-generation.md) | **Folded into `medical_devices/schedule/foundation.md` (F6 + Ground Rule 6), 2026-08-23** — no longer a deferred track; this file now lives on as a living pitfall-table reference every track appends to as it builds. Not medical-devices-specific despite living in that plan's Foundation — the rule applies repo-wide. |

Finished plans are removed from this index once done — the shipped
behavior is documented in the code's own `CLAUDE.md`/architecture docs,
not preserved here. (Postgres backend and crash/interrupt recovery were
both here; both shipped and are now covered by `Database/CLAUDE.md` /
`util/CLAUDE.md` and `harpia.architecture.md` respectively.
`message-versioning.md` — stable wire field numbers, JSON/XML
parse-boundary hardening, and a capability handshake across all four
transports — shipped 2026-08-22/23 and was removed 2026-08-23; its
design rationale is now distributed across `message/CLAUDE.md`,
`Capability/CLAUDE.md`, and the three `*CapabilityAdapter/CLAUDE.md`
files it fed. The one unrelated finding it surfaced — a `third_party/asio`
vendoring gap — wasn't part of the plan and lives on in
`NEXT_SESSION.md` as its own open item.)

## Backlog

Open items not yet big enough for their own scoping doc. Moved here from
`NEXT_SESSION.md`, which is a short-lived handoff note (what just happened,
what to check first) rather than a place to accumulate a durable backlog.
Add to this list piecemeal as items get scoped or come up — no need to do it
all at once.

- **Python as language #3** (after Java, see `multi-language-targets/`
  above) — see `multi-language-targets/README.md` §4 for the selection
  history. Multi-session sized, don't start as a "quick session."
- **Smaller/unscoped:** no YAML serialization, no multi-tier RBAC (single
  flat credential everywhere).
