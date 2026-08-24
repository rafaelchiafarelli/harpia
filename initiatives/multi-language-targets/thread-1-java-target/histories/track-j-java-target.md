# Java target — session breakdown

Session IDs below use a `J.<n>` prefix (J for Java) purely as a compact
label — not a reference to `harpia_medical_master_plan.md`'s track
lettering. This plan is standalone and general-purpose, not
medical-devices-specific; the one place it
touches that other plan is a real, narrow link, called out in Receives/
Gives below, not a shared identity.

**Corrected 2026-08-23 (was stale):** this used to say Python, per
`multi-language-targets.md`'s original recommendation. **Java** was
picked instead as the actual second target (2026-08-22 addendum): an
existing Android fleet wants harpia-generated Java code now, a concrete
business reason, not a re-litigation of the abstract Python-vs-Java cost
comparison.

**Re-graded 2026-08-23: this file originally reused `java-target.md`'s
own 8-slice order almost as-is** (only splitting DB by dialect and
REST/SOAP by transport) — each "slice" bundled several independent
deliverables into one sitting (e.g. the old "DB/CRUDL/migration, SQLite"
slice bundled scaffolding, bind/extract, and full CRUDL together).
Rebuilt below at a finer grain: one deliverable, its own tests, sized to
fit a single sitting — 27 sessions instead of 10. Consistent with this
thread's own scale check (`../README.md` §8): comparable to, or larger
than, the Postgres-backend effort, which itself was an 8-slice branch
plan before anyone tried to fit it into single-sitting sessions.

## Receives (must be done before this track starts)

- **Nothing from another plan.** This is general-purpose harpia
  capability, not gated on the medical-compliance plan's Foundation.
  Stages 0–6 (front-end) and `.proto` emission are already
  language-agnostic, shipped infrastructure this track reuses as-is —
  see `../README.md` §2.
- **Conditional, not a hard blocker:** if a consumer wants the Java
  target to be compliance-aware (respect `risk_class`/`phi` the way the
  C++ target does once `harpia_medical_master_plan.md`'s Foundation
  lands), that's an additional concern layered on top — not yet scoped
  in its own file (there's no separate thin-pointer file under
  `medical_devices/epics/thread-4-platform-infra/` for it) — not a
  precondition for the sessions below.

## Gives (what "done" means here, consumed by whom)

- A full, symmetric Java generation target (Stages 8–14 emitters) plus a
  verified Android-consumption path (message classes, JSON, gRPC/ZMQ
  clients) for the fleet that actually motivates this work.
- **Consumed by:** the external Android fleet driving this work.
  `harpia_medical_master_plan.md`'s Track J references this as the real
  session breakdown rather than duplicating it — see that plan's own
  thin pointer file.

## Files this track touches

- New per-language emitter directories, mirroring `Database/`,
  `JsonAdapter/`, etc. **Flag:** neither `../README.md` nor this file
  commits to specific new directory names (e.g. a `JavaDatabase/`-shaped
  package) — not guessing names ahead of the first session actually
  creating them.

---


## Watch for

- J.1's codegen-timing decision and J.24's runtime-variant decision are
  the two forks `../README.md` §4 calls out as having "no single
  obviously-correct answer" — don't default either one silently. **J.1
  resolved 2026-08-23: build-time codegen** (`.proto` +
  `build.gradle`/`protobuf-gradle-plugin`, not a harpia-side
  `protoc`/`protoc-gen-grpc-java` shell-out) — see
  `gRPC-wiring/codegen-timing-decision.md`. **J.24 resolved 2026-08-23:
  full protobuf-java runtime** (not `javalite`) — see
  `Android-consumption/protobuf-runtime-variant-decision.md`, including
  its explicit caveat that this wasn't verified against a real Android
  build (no SDK/emulator available where it was made).
- Schema-evolution/migration support for the Java DB layer is explicitly
  not scoped in J.5–J.9 — flagged there, don't assume it's implied.
- Don't extrapolate this track's Java-specific costs to Rust/Node ahead
  of time — same discipline previously applied to Python: Python's
  cost analysis wasn't extrapolated to Rust/Node/Java by analogy either,
  because language-specific facts (reflection API shape, protobuf JSON
  support, etc.) don't transfer across a different type system or
  runtime-reflection story. Python is still the next language after
  Java, not dropped.
- If a compliance-aware layer for the Java target is picked up under
  `medical_devices/epics/thread-4-platform-infra/`, keep this file as the
  source of truth for the session breakdown — don't let a duplicate
  breakdown grow there.
