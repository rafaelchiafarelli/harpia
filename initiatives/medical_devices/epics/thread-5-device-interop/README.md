# Thread 5 — Device Interoperability

Same restructuring as `thread-1-data-and-keys/` (see that folder's
README for the full rationale): one file per track, each broken into
small `Session <Track>.<n>` units (one deliverable + its own tests,
sized to fit a single sitting), each with an explicit Receives/Gives/
Files-touched contract.

Added after the original four sessions were scoped — see the master
plan's 2026-08-21 update note. Three tracks — the master plan's §3 always
said "Track P → Track Q → Track R," but the original
`session-5-device-interop.md` never actually included Track R; that gap
is closed in this restructuring (see `track-r-fhir-facade.md`'s own
note). Track Q and Track R are both explicitly scoping/design work this
pass, not full implementation — smaller in total than Thread 1 or
Thread 2.

- [track-p-dds-transport.md](histories/dds-transport/track-p-dds-transport.md) — DDS transport
  adapter (ASTM F2761/OpenICE-class bedside device bus).
- [track-q-sdc-biceps.md](histories/sdc-biceps/track-q-sdc-biceps.md) — IEEE 11073 SDC/BICEPS
  device-interop bindings (scoping + WS-Discovery responder only).
- [track-r-fhir-facade.md](histories/fhir-facade/track-r-fhir-facade.md) — HL7 FHIR façade
  (design doc already done; one worked example remaining this pass).

---

## What this whole thread receives from Foundation

- **F1** — `ComplianceContext` threaded through `main.py` and every stage.
- **F2** — `field.is_phi` flag available on every parsed field (Track Q
  needs this).
- **F3** — `AuditSink` (no-op stub) exists and is injectable.
- **F5** — `CryptoBackend` selection seam exists — Track P's DDS-Security
  wiring links against this, not its own crypto library.
- **F4** — a tagged regression baseline exists.

Same precondition set as Thread 2's Track C (F1, F3, F5), plus F2 for
Track Q specifically (see `../foundation.md`).

---

## Execution order across tracks

**Track P → Track Q → Track R, same session-line.** No hard file
dependency between any of the three, but each later track benefits from
the one before it as a worked precedent: Track Q's design work leans on
Track P's QoS/delivery-guarantee mapping for how a new transport ties
into `phi`/`critical` schema-level modifiers; Track R's design work
similarly leans on Track Q's schema-field-to-external-vocabulary mapping
question, being the same kind of problem (LOINC/SNOMED terminology
binding vs. BICEPS Metric/Alert/Context binding).

If Thread 2 finishes its sessions early, it can pick up Track P as a
next task instead of this being a strictly separate thread — but keep
P → Q → R sequential regardless of which session-line executes them.

---

## Definition of done (every session, every track in this thread)

- Unit tests for the construct/behavior that specific session introduces.
- Integration test covering end-to-end behavior — for Track P, an actual
  DDS publish/subscribe exchange under the specified QoS, not just unit
  tests of the QoS-mapping logic in isolation.
- Full F4 regression baseline still passes.
- Track P specifically: one-paragraph `ComplianceReport/` note (feeds
  Track M later), same rule Thread 2 applies to Track C.
- Track Q's design doc is reviewed against
  `harpia_sensitive_data_design_rules.md` before any of its grammar
  hypothesis gets implemented in a later track — don't let the mapping
  guess ship as fact.
- **Ground Rule 6 (`../foundation.md`, added 2026-08-23):** any session
  that touches a consumer-facing template/adapter emits/updates accurate
  Doxygen doc-comments for what it touched, in the same session — not
  deferred. Add a row to `initiatives/doxygen-generation/doxygen-generation.md` §4 if the work
  surfaces a pitfall not already listed there.

## Watch for

- Track P's DDS-Security config is part of the single project-wide
  `risk_class` floor, same as Track B/C — no per-variant parity job to
  feed (dropped entirely per `harpia_medical_master_plan.md` §0a).
- Don't let Track Q's scoping work quietly turn into implementation
  mid-session — the deliverable is a design doc + WS-Discovery responder,
  not a working BICEPS stack. If a session-line has spare capacity after
  both tracks, pull from the backlog (`initiatives/README.md`) rather than
  scope-creep Track Q.
